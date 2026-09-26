use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::{Child, Command};
use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::Mutex;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager};

mod legend_lore;

// ---------------------------------------------------------------------------
// Sidecar state — holds the Python child process handle and any startup
// failure payload. The failure is stashed so the frontend can pull it on
// mount even though the emit happens during setup() (before the webview
// has loaded a listener).
// ---------------------------------------------------------------------------

struct SidecarState(Mutex<Option<Child>>);

struct SidecarFailureState(Mutex<Option<SidecarFailedPayload>>);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Serialize, Clone, Debug)]
struct SidecarFailedPayload {
    log_path: String,
    message: String,
}

// ---------------------------------------------------------------------------
// Window size — persisted in logical pixels
// ---------------------------------------------------------------------------

/// A window size in logical (DPI-independent) pixels.
///
/// Logical is the only unit that survives a move between displays with
/// different scale factors, and it's the unit tauri.conf.json already speaks.
/// tauri-plugin-window-state stored physical pixels instead, so a size saved
/// on a 1x display came back halved on a 2x one.
#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq)]
struct WindowSize {
    width: f64,
    height: f64,
}

/// Mirrors minWidth/minHeight in tauri.conf.json.
const MIN_WINDOW_WIDTH: f64 = 940.0;
const MIN_WINDOW_HEIGHT: f64 = 600.0;

/// Bring a restored size into range, or reject it outright.
///
/// Never trust what's on disk. AppKit enforces NSWindow.minSize only on
/// interactive resize, so a programmatic set_size below the floor sticks until
/// the user drags an edge — that snap was the whole symptom of the old bug.
///
/// `max` is the current monitor's logical size when it's known, so a size
/// saved on a large display can't overflow a smaller one. The floor wins if a
/// monitor is somehow narrower than it.
fn sanitize_window_size(saved: WindowSize, max: Option<WindowSize>) -> Option<WindowSize> {
    if !saved.width.is_finite() || !saved.height.is_finite() {
        return None;
    }
    if saved.width <= 0.0 || saved.height <= 0.0 {
        return None;
    }

    let (max_width, max_height) = match max {
        Some(m) if m.width.is_finite() && m.height.is_finite() => (m.width, m.height),
        _ => (f64::INFINITY, f64::INFINITY),
    };

    Some(WindowSize {
        width: saved.width.min(max_width).max(MIN_WINDOW_WIDTH),
        height: saved.height.min(max_height).max(MIN_WINDOW_HEIGHT),
    })
}

fn window_size_path(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    app.path()
        .app_data_dir()
        .ok()
        .map(|dir| dir.join("window.json"))
}

/// Apply the size the user last left the window at.
///
/// Called early in setup(), before the sidecar startup blocks: restoring after
/// it would leave the window at its default size for a couple of seconds and
/// then jump.
fn restore_window_size(app: &tauri::AppHandle) {
    let Some(path) = window_size_path(app) else {
        return;
    };
    let Ok(raw) = std::fs::read_to_string(&path) else {
        return;
    };
    let Ok(saved) = serde_json::from_str::<WindowSize>(&raw) else {
        return;
    };
    let Some(window) = app.get_webview_window("main") else {
        return;
    };

    let max = window.current_monitor().ok().flatten().map(|monitor| {
        let size = monitor.size().to_logical::<f64>(monitor.scale_factor());
        WindowSize {
            width: size.width,
            height: size.height,
        }
    });

    if let Some(size) = sanitize_window_size(saved, max) {
        let _ = window.set_size(tauri::LogicalSize::new(size.width, size.height));
    }
}

/// Record the window's current size, in logical pixels.
///
/// Skips a hidden window: closing hides to the tray, and a hidden frame isn't
/// what the user last saw.
fn save_window_size(app: &tauri::AppHandle, label: &str) {
    let Some(window) = app.get_webview_window(label) else {
        return;
    };
    if !window.is_visible().unwrap_or(false) {
        return;
    }
    let Ok(scale) = window.scale_factor() else {
        return;
    };
    let Ok(physical) = window.inner_size() else {
        return;
    };
    let Some(path) = window_size_path(app) else {
        return;
    };

    let logical = physical.to_logical::<f64>(scale);
    let size = WindowSize {
        width: logical.width,
        height: logical.height,
    };
    if let Ok(json) = serde_json::to_string(&size) {
        let _ = std::fs::write(path, json);
    }
}

// ---------------------------------------------------------------------------
// Sidecar port and health checks (sidecar, models, MCP). legend_lore.rs
// reaches the sidecar through sidecar_url() as well.
// ---------------------------------------------------------------------------

/// Port the sidecar bound at startup, published via ``data_dir/sidecar.port``.
/// Zero means the sidecar has not come up yet — every command that calls it
/// will fail-fast with a connection error in that case, which is the same
/// outcome as a sidecar crash mid-session.
static SIDECAR_PORT: AtomicU16 = AtomicU16::new(0);

fn sidecar_url() -> String {
    format!("http://127.0.0.1:{}", SIDECAR_PORT.load(Ordering::Relaxed))
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ModelStatus {
    role: String,
    runtime: String,
    model: String,
    runtime_up: bool,
    ready: bool,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ModelsStatus {
    models: Vec<ModelStatus>,
}

/// Readiness of the ML models the sidecar depends on, one row per role.
/// The sidecar owns the probe (it knows which runtime serves which
/// model); this is a plain proxy, like `check_mcp_status`.
#[tauri::command]
async fn check_models_status() -> Result<ModelsStatus, String> {
    let client = reqwest::Client::new();
    match client
        .get(format!("{}/api/models/status", sidecar_url()))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => resp
            .json::<ModelsStatus>()
            .await
            .map_err(|e| format!("Failed to parse models status: {}", e)),
        _ => Ok(ModelsStatus { models: vec![] }),
    }
}

#[tauri::command]
async fn check_sidecar_health() -> Result<bool, String> {
    let client = reqwest::Client::new();
    match client
        .get(format!("{}/health", sidecar_url()))
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct McpStatus {
    connected: bool,
    active: bool,
}

#[tauri::command]
async fn check_mcp_status() -> Result<McpStatus, String> {
    let client = reqwest::Client::new();
    match client
        .get(format!("{}/api/mcp-status", sidecar_url()))
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => {
            resp.json::<McpStatus>().await.map_err(|e| e.to_string())
        }
        _ => Ok(McpStatus {
            connected: false,
            active: false,
        }),
    }
}

#[tauri::command]
fn get_data_dir(app: tauri::AppHandle) -> Result<String, String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("Failed to resolve app data directory: {}", e))?;
    Ok(dir.to_string_lossy().into_owned())
}

// ---------------------------------------------------------------------------
// Tauri commands — MCP config generation
// ---------------------------------------------------------------------------

#[tauri::command]
fn get_mcp_config(app_handle: tauri::AppHandle) -> Result<String, String> {
    // MCP server is launched in a separate process by Claude Desktop, so it
    // can't share our in-memory port. We hand it the data dir instead and let
    // it read sidecar.port at startup — that file follows the ephemeral port
    // the sidecar binds at every launch.
    let data_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("Failed to resolve app data directory: {}", e))?
        .join("chroma_db")
        .to_string_lossy()
        .into_owned();

    let (command, args) = if cfg!(debug_assertions) {
        // Dev mode: use source-tree Python.
        //
        // Canonicalize the sidecar directory (resolves `..` and gives us an
        // absolute path) BUT NOT the venv python binary itself: that binary
        // is a symlink to the system Python, and following the symlink
        // breaks venv activation. CPython locates pyvenv.cfg by walking up
        // from sys.executable; if sys.executable is the canonicalized
        // homebrew path it never finds the venv, so installed packages
        // (httpx, mcp, …) aren't on sys.path.
        let sidecar_dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../sidecar")
            .canonicalize()
            .map_err(|e| format!("Cannot find sidecar dir: {}", e))?;

        let mcp_server_py = sidecar_dir
            .join("mcp_server.py")
            .to_string_lossy()
            .into_owned();

        let venv_python = sidecar_dir.join(".venv/bin/python3");
        let python_path = if venv_python.exists() {
            venv_python.to_string_lossy().into_owned()
        } else {
            "python3".to_string()
        };

        (
            python_path,
            vec![mcp_server_py, "--data-dir".to_string(), data_dir],
        )
    } else {
        // Production: bundled externalBin sidecar
        let binary = sidecar_binary_path("legend-lore-mcp")?
            .to_string_lossy()
            .into_owned();
        (binary, vec!["--data-dir".to_string(), data_dir])
    };

    let config = serde_json::json!({
        "mcpServers": {
            "Legend Lore": {
                "command": command,
                "args": args,
            }
        }
    });

    serde_json::to_string_pretty(&config).map_err(|e| format!("Failed to serialize config: {}", e))
}

// ---------------------------------------------------------------------------
// Bundled binary resolution
// ---------------------------------------------------------------------------

/// Resolve a Tauri `externalBin` sidecar binary at runtime.
///
/// Tauri strips the target-triple suffix at bundle time and places the binary
/// next to the main app executable (Contents/MacOS/ on macOS, alongside the
/// main exe on Windows and Linux). So we find it by walking out of the current
/// executable's directory.
fn sidecar_binary_path(name: &str) -> Result<std::path::PathBuf, String> {
    let exe = std::env::current_exe()
        .map_err(|e| format!("Failed to resolve current executable: {}", e))?;
    let exe_dir = exe
        .parent()
        .ok_or_else(|| "Current executable has no parent directory".to_string())?;

    let filename = if cfg!(windows) {
        format!("{}.exe", name)
    } else {
        name.to_string()
    };
    let path = exe_dir.join(&filename);

    if !path.exists() {
        return Err(format!(
            "Sidecar binary '{}' not found at {}",
            name,
            path.display()
        ));
    }
    Ok(path)
}

// ---------------------------------------------------------------------------
// Sidecar lifecycle
// ---------------------------------------------------------------------------

/// Return the stashed startup-failure payload, if any. The frontend calls
/// this on mount to recover from the race where ``setup()`` emits
/// ``sidecar://failed`` before the webview has loaded a listener.
#[tauri::command]
fn get_sidecar_failure(state: tauri::State<SidecarFailureState>) -> Option<SidecarFailedPayload> {
    state.0.lock().ok().and_then(|g| g.clone())
}

/// Block until the sidecar publishes its port file and accepts a TCP
/// connection, then return the bound port. Errors carry a single
/// human-readable message — the caller is responsible for surfacing it.
///
/// The sidecar binds with ``--port 0`` so the OS assigns a free port; we
/// learn what that port is by polling for ``data_dir/sidecar.port`` to
/// appear. PyInstaller ``--onefile`` extraction in production can take a
/// few seconds on first run, hence the longer attempt budget there.
fn wait_for_sidecar(port_file: &Path, log_path: &Path) -> Result<u16, String> {
    use std::net::TcpStream;
    use std::time::Duration;

    let max_attempts: u32 = if cfg!(debug_assertions) { 50 } else { 150 };
    let connect_timeout = Duration::from_millis(200);

    for attempt in 1..=max_attempts {
        if let Ok(contents) = std::fs::read_to_string(port_file) {
            if let Ok(port) = contents.trim().parse::<u16>() {
                let addr = format!("127.0.0.1:{}", port);
                if let Ok(socket_addr) = addr.parse() {
                    if TcpStream::connect_timeout(&socket_addr, connect_timeout).is_ok() {
                        println!("Sidecar ready on port {} after {} attempts", port, attempt);
                        return Ok(port);
                    }
                }
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }

    let mut log_tail = String::new();
    if let Ok(log_contents) = std::fs::read_to_string(log_path) {
        if !log_contents.is_empty() {
            log_tail = log_contents
                .lines()
                .rev()
                .take(20)
                .collect::<Vec<_>>()
                .into_iter()
                .rev()
                .collect::<Vec<_>>()
                .join("\n");
        }
    }

    let mut msg = format!(
        "Sidecar did not become ready within timeout. Check log at {}",
        log_path.display()
    );
    if !log_tail.is_empty() {
        msg.push_str(&format!("\n--- last 20 lines ---\n{}", log_tail));
    }
    Err(msg)
}

fn start_sidecar(data_dir: &Path) -> Result<Child, String> {
    let (program, base_args): (std::path::PathBuf, Vec<String>) = if cfg!(debug_assertions) {
        // Dev mode: use source-tree Python
        let sidecar_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../sidecar");
        let server_py = sidecar_dir.join("server.py");

        if !server_py.exists() {
            return Err(format!("Sidecar not found at: {}", server_py.display()));
        }

        let venv_python = sidecar_dir.join(".venv/bin/python3");
        let python = if venv_python.exists() {
            venv_python
        } else {
            std::path::PathBuf::from("python3")
        };

        (python, vec![server_py.to_string_lossy().into_owned()])
    } else {
        // Production: bundled externalBin sidecar
        let binary = sidecar_binary_path("legend-lore-sidecar")?;
        (binary, vec![])
    };

    // Log sidecar stderr to a file for diagnostics (especially useful in
    // production builds where there is no terminal to observe output).
    let log_dir = data_dir.parent().unwrap_or(data_dir);
    let log_file = std::fs::File::create(log_dir.join("sidecar.log"))
        .map_err(|e| format!("Failed to create sidecar log file: {}", e))?;
    let stderr_file = log_file
        .try_clone()
        .map_err(|e| format!("Failed to clone log file handle: {}", e))?;

    // Stale port file from a previous run would mislead wait_for_sidecar.
    // Sidecar will rewrite it after it binds, but clear it now to be safe.
    let _ = std::fs::remove_file(data_dir.join("sidecar.port"));

    let mut cmd = Command::new(&program);
    cmd.args(&base_args)
        .arg("--port")
        .arg("0") // ephemeral — sidecar publishes the actual port to data_dir/sidecar.port
        .arg("--data-dir")
        .arg(data_dir.to_string_lossy().as_ref())
        .stdout(std::process::Stdio::from(log_file))
        .stderr(std::process::Stdio::from(stderr_file));

    // Put sidecar in its own process group so we can kill the entire group on exit
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }

    let child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start sidecar with {}: {}", program.display(), e))?;

    Ok(child)
}

fn stop_sidecar(state: &SidecarState) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(ref mut child) = *guard {
            // Send SIGTERM to the sidecar's process group for graceful shutdown
            #[cfg(unix)]
            {
                let pid = child.id() as i32;
                unsafe {
                    libc::kill(-pid, libc::SIGTERM);
                }
            }
            // Windows: child.kill() only terminates the immediate process via
            // TerminateProcess and leaves any subprocesses orphaned. taskkill
            // /T walks the process tree by parent PID, /F skips graceful exit.
            #[cfg(not(unix))]
            {
                let _ = Command::new("taskkill")
                    .args(["/T", "/F", "/PID", &child.id().to_string()])
                    .status();
            }

            // Wait up to 3 seconds for graceful exit, then force kill
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
            loop {
                match child.try_wait() {
                    Ok(Some(_)) => break,
                    Ok(None) if std::time::Instant::now() < deadline => {
                        std::thread::sleep(std::time::Duration::from_millis(100));
                    }
                    _ => {
                        let _ = child.kill();
                        let _ = child.wait();
                        break;
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// App entry point
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
/// v3.0.0 renamed the bundle identifier from `games.unseenservant.legendlore`
/// to `games.unseenservant.app`, which moves the app-data directory. Move the
/// old one across once so the index, settings and window geometry survive.
fn migrate_legacy_data_dir(app_data_dir: &Path) {
    if app_data_dir.exists() {
        return;
    }
    let Some(parent) = app_data_dir.parent() else {
        return;
    };
    let legacy = parent.join("games.unseenservant.legendlore");
    if legacy.is_dir() {
        if let Err(e) = std::fs::rename(&legacy, app_data_dir) {
            eprintln!(
                "Failed to migrate data dir from {}: {}",
                legacy.display(),
                e
            );
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![
            legend_lore::select_folder,
            legend_lore::list_files,
            legend_lore::count_pdfs_recursive,
            legend_lore::rename_file,
            legend_lore::delete_file,
            legend_lore::rename_folder,
            legend_lore::delete_folder,
            check_models_status,
            check_sidecar_health,
            check_mcp_status,
            legend_lore::get_index_status,
            legend_lore::sync_index,
            legend_lore::reindex_all,
            legend_lore::reindex_file,
            legend_lore::get_document_stats,
            legend_lore::get_stats,
            legend_lore::delete_index,
            get_data_dir,
            legend_lore::get_known_game_systems,
            legend_lore::set_game_systems,
            legend_lore::create_custom_game_system,
            legend_lore::update_custom_game_system,
            legend_lore::delete_custom_game_system,
            legend_lore::toggle_builtin_game_system,
            get_mcp_config,
            legend_lore::get_collections,
            legend_lore::create_collection,
            legend_lore::update_collection,
            legend_lore::rename_collection,
            legend_lore::delete_collection,
            get_sidecar_failure,
            legend_lore::search_index,
            legend_lore::get_search_settings,
            legend_lore::update_search_settings
        ])
        .setup(|app| {
            // Determine where ChromaDB should store data
            let app_data_dir = app
                .path()
                .app_data_dir()
                .expect("Failed to resolve app data directory");
            migrate_legacy_data_dir(&app_data_dir);
            std::fs::create_dir_all(&app_data_dir).ok();

            // Before the sidecar startup below, which blocks.
            restore_window_size(app.handle());

            let chroma_dir = app_data_dir.join("chroma_db");

            let sidecar_log = app_data_dir.join("sidecar.log");

            app.manage(SidecarFailureState(Mutex::new(None)));

            // record_failure: stash for the frontend's late mount AND emit for
            // any listener that's already attached (e.g. mid-session restart).
            let record_failure = |app: &tauri::AppHandle, payload: SidecarFailedPayload| {
                if let Some(state) = app.try_state::<SidecarFailureState>() {
                    if let Ok(mut guard) = state.0.lock() {
                        *guard = Some(payload.clone());
                    }
                }
                let _ = app.emit("sidecar://failed", &payload);
            };

            // Start the Python sidecar
            let port_file = chroma_dir.join("sidecar.port");
            match start_sidecar(&chroma_dir) {
                Ok(child) => {
                    println!("Sidecar started (PID: {})", child.id());
                    app.manage(SidecarState(Mutex::new(Some(child))));
                    match wait_for_sidecar(&port_file, &sidecar_log) {
                        Ok(port) => {
                            SIDECAR_PORT.store(port, Ordering::Relaxed);
                        }
                        Err(msg) => {
                            eprintln!("{}", msg);
                            record_failure(
                                app.handle(),
                                SidecarFailedPayload {
                                    log_path: sidecar_log.to_string_lossy().into_owned(),
                                    message: msg,
                                },
                            );
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Warning: Could not start sidecar: {}", e);
                    eprintln!("Indexing features will be unavailable.");
                    app.manage(SidecarState(Mutex::new(None)));
                    record_failure(
                        app.handle(),
                        SidecarFailedPayload {
                            log_path: sidecar_log.to_string_lossy().into_owned(),
                            message: format!("Could not start sidecar: {}", e),
                        },
                    );
                }
            }

            // ---------------------------------------------------------------
            // System tray
            // ---------------------------------------------------------------
            let show_item = MenuItem::with_id(app, "show", "Show", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &quit_item])?;

            TrayIconBuilder::new()
                .icon(tauri::include_image!("icons/tray-icon.png"))
                .icon_as_template(true)
                .tooltip("Unseen Servant")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri application")
        .run(|app_handle, event| {
            match event {
                tauri::RunEvent::WindowEvent {
                    label,
                    event: tauri::WindowEvent::CloseRequested { api, .. },
                    ..
                } => {
                    // Hide window instead of closing — app stays alive in tray
                    api.prevent_close();
                    save_window_size(app_handle, &label);
                    if let Some(window) = app_handle.get_webview_window(&label) {
                        let _ = window.hide();
                    }
                }
                tauri::RunEvent::ExitRequested { api, code, .. } => {
                    if code.is_some() {
                        // Triggered by app.exit() (tray Quit or Cmd+Q) — let it proceed.
                        // No-op when quitting from the tray: the window is already
                        // hidden, so CloseRequested saved the size we want.
                        save_window_size(app_handle, "main");
                    } else {
                        // Triggered by last window hiding — keep app alive in tray
                        api.prevent_exit();
                    }
                }
                #[cfg(target_os = "macos")]
                tauri::RunEvent::Reopen { .. } => {
                    // macOS: user clicked dock icon while app is running
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.unminimize();
                        let _ = window.set_focus();
                    }
                }
                tauri::RunEvent::Exit => {
                    let state = app_handle.state::<SidecarState>();
                    stop_sidecar(state.inner());
                    println!("Sidecar stopped.");
                }
                _ => {}
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_window_size_raises_a_too_small_value_to_the_floor() {
        // The exact regression: 940x600 physical, saved on the 1x external,
        // arrived as 470x300 logical on the 2x built-in and stuck there until
        // the user grabbed an edge.
        let got = sanitize_window_size(
            WindowSize {
                width: 470.0,
                height: 300.0,
            },
            None,
        );
        assert_eq!(
            got,
            Some(WindowSize {
                width: MIN_WINDOW_WIDTH,
                height: MIN_WINDOW_HEIGHT,
            })
        );
    }

    #[test]
    fn sanitize_window_size_caps_to_the_current_monitor() {
        // Saved on the 2560x1440 external, restored on the 1728x1117 built-in.
        let monitor = Some(WindowSize {
            width: 1728.0,
            height: 1117.0,
        });
        let got = sanitize_window_size(
            WindowSize {
                width: 2400.0,
                height: 1300.0,
            },
            monitor,
        );
        assert_eq!(
            got,
            Some(WindowSize {
                width: 1728.0,
                height: 1117.0,
            })
        );
    }

    #[test]
    fn sanitize_window_size_keeps_the_floor_when_the_monitor_is_smaller() {
        let monitor = Some(WindowSize {
            width: 800.0,
            height: 500.0,
        });
        let got = sanitize_window_size(
            WindowSize {
                width: 1280.0,
                height: 800.0,
            },
            monitor,
        );
        assert_eq!(
            got,
            Some(WindowSize {
                width: MIN_WINDOW_WIDTH,
                height: MIN_WINDOW_HEIGHT,
            })
        );
    }

    #[test]
    fn sanitize_window_size_passes_a_reasonable_value_through() {
        let monitor = Some(WindowSize {
            width: 2560.0,
            height: 1440.0,
        });
        let size = WindowSize {
            width: 1400.0,
            height: 900.0,
        };
        assert_eq!(sanitize_window_size(size, monitor), Some(size));
    }

    #[test]
    fn sanitize_window_size_rejects_garbage() {
        let bad = [
            (f64::NAN, 600.0),
            (f64::INFINITY, 600.0),
            (1280.0, f64::NAN),
            (0.0, 600.0),
            (-1280.0, 600.0),
            (1280.0, -600.0),
        ];
        for (width, height) in bad {
            assert_eq!(
                sanitize_window_size(WindowSize { width, height }, None),
                None,
                "expected {width}x{height} to be rejected"
            );
        }
    }
}

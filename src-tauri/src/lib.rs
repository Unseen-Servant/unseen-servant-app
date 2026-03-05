use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tauri::{Emitter, Manager};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::menu::{Menu, MenuItem};
use std::process::{Child, Command};
use std::sync::Mutex;

// ---------------------------------------------------------------------------
// Sidecar state — holds the Python child process handle
// ---------------------------------------------------------------------------

struct SidecarState(Mutex<Option<Child>>);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug, Clone)]
struct FileItem {
    name: String,
    path: String,
    is_dir: bool,
    children: Option<Vec<FileItem>>,
}

#[derive(Serialize, Deserialize, Debug)]
struct IndexResult {
    indexed: u32,
    total: u32,
    errors: Vec<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct FileStatusEntry {
    path: String,
    filename: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    chunk_count: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    game_system: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct FileErrorEntry {
    path: String,
    error: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct IndexStatusSummary {
    add: u32,
    remove: u32,
    update: u32,
    up_to_date: u32,
    errors: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct IndexStatusResult {
    to_add: Vec<FileStatusEntry>,
    to_remove: Vec<FileStatusEntry>,
    to_update: Vec<FileStatusEntry>,
    up_to_date: Vec<FileStatusEntry>,
    errors: Vec<FileErrorEntry>,
    summary: IndexStatusSummary,
}

#[derive(Serialize, Deserialize, Debug)]
struct SyncResult {
    added: u32,
    removed: u32,
    updated: u32,
    errors: Vec<String>,
    total_indexed: u32,
    chunks_total: u32,
}

#[derive(Serialize, Clone, Debug)]
struct SyncProgressPayload {
    files_done: u32,
    total_files: u32,
    chunks_total: u32,
    current_file: String,
    phase: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct GameSystemsResult {
    game_systems: Vec<String>,
    count: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct SetGameSystemResult {
    filename: String,
    game_system: String,
    chunks_updated: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct KnownGameSystem {
    tag: String,
    game_system: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct KnownGameSystemsResult {
    systems: Vec<KnownGameSystem>,
}

#[derive(Serialize, Deserialize, Debug)]
struct CollectionInfo {
    name: String,
    file_paths: Vec<String>,
    file_count: u32,
    created_at: String,
    description: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct CollectionsResult {
    collections: std::collections::HashMap<String, CollectionInfo>,
    count: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct CollectionMutationResult {
    name: String,
    file_count: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct CollectionDeleteResult {
    message: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct StatsResult {
    total_chunks: u32,
    total_documents: u32,
    collection_name: String,
    storage_bytes: u64,
}

// ---------------------------------------------------------------------------
// Tauri commands — file system
// ---------------------------------------------------------------------------

#[tauri::command]
async fn select_folder(app: tauri::AppHandle) -> Result<String, String> {
    use tauri_plugin_dialog::DialogExt;

    let folder = app.dialog()
        .file()
        .set_title("Select your TTRPG folder")
        .blocking_pick_folder();

    match folder {
        Some(path) => Ok(path.to_string()),
        None => Err("No folder selected".to_string()),
    }
}

#[tauri::command]
fn list_files(folder_path: String) -> Result<Vec<FileItem>, String> {
    let mut items = Vec::new();
    let folder = Path::new(&folder_path);

    if !folder.is_dir() {
        return Err("Path is not a directory".to_string());
    }

    for entry in fs::read_dir(folder).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let metadata = entry.metadata().map_err(|e| e.to_string())?;
        let file_type = metadata.file_type();
        let is_dir = file_type.is_dir();
        let name = entry.file_name().to_string_lossy().into_owned();
        let path = folder.join(&name).to_string_lossy().into_owned();
        let is_pdf = !is_dir && name.to_lowercase().ends_with(".pdf");

        if is_dir || is_pdf {
            items.push(FileItem {
                name,
                path,
                is_dir,
                children: None,
            });
        }
    }

    // Sort: folders first, then alphabetically (case-insensitive)
    items.sort_by(|a, b| {
        b.is_dir.cmp(&a.is_dir)
            .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
    });

    Ok(items)
}

// ---------------------------------------------------------------------------
// Tauri commands — indexing (calls the Python sidecar via HTTP)
// ---------------------------------------------------------------------------

const SIDECAR_URL: &str = "http://localhost:8420";

#[tauri::command]
async fn check_sidecar_health() -> Result<bool, String> {
    let client = reqwest::Client::new();
    match client
        .get(format!("{}/health", SIDECAR_URL))
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

#[tauri::command]
async fn index_files(paths: Vec<String>) -> Result<IndexResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/index-files", SIDECAR_URL))
        .json(&serde_json::json!({ "paths": paths }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: IndexResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn get_index_status(paths: Vec<String>) -> Result<IndexStatusResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/index-status", SIDECAR_URL))
        .json(&serde_json::json!({ "selected_paths": paths }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: IndexStatusResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn sync_index(app: tauri::AppHandle, paths: Vec<String>) -> Result<SyncResult, String> {
    use futures_util::StreamExt;

    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/sync-index-stream", SIDECAR_URL))
        .json(&serde_json::json!({ "selected_paths": paths }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let mut stream = response.bytes_stream();
    let mut buffer = String::new();
    let mut final_result: Option<SyncResult> = None;

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("Stream error: {}", e))?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));

        while let Some(pos) = buffer.find("\n\n") {
            let frame = buffer[..pos].to_string();
            buffer = buffer[pos + 2..].to_string();

            if let Some(data) = frame.strip_prefix("data: ") {
                if let Ok(json) = serde_json::from_str::<serde_json::Value>(data) {
                    match json.get("event").and_then(|e| e.as_str()) {
                        Some("started") => {
                            let payload = SyncProgressPayload {
                                files_done: 0,
                                total_files: json["total_files"]
                                    .as_u64()
                                    .unwrap_or(0)
                                    as u32,
                                chunks_total: 0,
                                current_file: String::new(),
                                phase: String::new(),
                            };
                            let _ = app.emit("sync-progress", &payload);
                        }
                        Some("progress") => {
                            let payload = SyncProgressPayload {
                                files_done: json["files_done"].as_u64().unwrap_or(0) as u32,
                                total_files: json["total_files"].as_u64().unwrap_or(0) as u32,
                                chunks_total: json["chunks_total"].as_u64().unwrap_or(0) as u32,
                                current_file: json["current_file"]
                                    .as_str()
                                    .unwrap_or("")
                                    .to_string(),
                                phase: json["phase"].as_str().unwrap_or("").to_string(),
                            };
                            let _ = app.emit("sync-progress", &payload);
                        }
                        Some("complete") => {
                            final_result = serde_json::from_value(serde_json::json!({
                                "added": json["added"],
                                "removed": json["removed"],
                                "updated": json["updated"],
                                "errors": json["errors"],
                                "total_indexed": json["total_indexed"],
                                "chunks_total": json["chunks_total"],
                            }))
                            .ok();
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    final_result.ok_or_else(|| "Sync completed but no result received".to_string())
}

// ---------------------------------------------------------------------------
// Tauri commands — game system management
// ---------------------------------------------------------------------------

#[tauri::command]
async fn get_game_systems() -> Result<GameSystemsResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/game-systems", SIDECAR_URL))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: GameSystemsResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn get_known_game_systems() -> Result<KnownGameSystemsResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/known-game-systems", SIDECAR_URL))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: KnownGameSystemsResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn get_stats() -> Result<StatsResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/stats", SIDECAR_URL))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: StatsResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn set_game_system(filename: String, game_system: String) -> Result<SetGameSystemResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/set-game-system", SIDECAR_URL))
        .json(&serde_json::json!({
            "filename": filename,
            "game_system": game_system,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        return Err(format!("Sidecar error: {}", response.status()));
    }

    let result: SetGameSystemResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

// ---------------------------------------------------------------------------
// Tauri commands — collections
// ---------------------------------------------------------------------------

#[tauri::command]
async fn get_collections() -> Result<CollectionsResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/collections", SIDECAR_URL))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: CollectionsResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn create_collection(
    name: String,
    file_paths: Vec<String>,
    description: String,
) -> Result<CollectionMutationResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/collections", SIDECAR_URL))
        .json(&serde_json::json!({
            "name": name,
            "file_paths": file_paths,
            "description": description,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: CollectionMutationResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn update_collection(
    name: String,
    file_paths: Vec<String>,
    description: Option<String>,
) -> Result<CollectionMutationResult, String> {
    let client = reqwest::Client::new();
    let mut body = serde_json::json!({
        "file_paths": file_paths,
    });
    if let Some(desc) = description {
        body["description"] = serde_json::Value::String(desc);
    }

    let response = client
        .put(format!("{}/api/collections/{}", SIDECAR_URL, name))
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: CollectionMutationResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn delete_collection(name: String) -> Result<CollectionDeleteResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .delete(format!("{}/api/collections/{}", SIDECAR_URL, name))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: CollectionDeleteResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

// ---------------------------------------------------------------------------
// Tauri commands — MCP config generation
// ---------------------------------------------------------------------------

#[tauri::command]
fn get_mcp_config() -> Result<String, String> {
    let sidecar_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../sidecar");

    let mcp_server_py = sidecar_dir
        .join("mcp_server.py")
        .canonicalize()
        .map_err(|e| format!("Cannot find mcp_server.py: {}", e))?;

    let venv_python = sidecar_dir.join(".venv/bin/python3");
    let python_path = if venv_python.exists() {
        venv_python
            .canonicalize()
            .map_err(|e| format!("Cannot resolve Python path: {}", e))?
            .to_string_lossy()
            .into_owned()
    } else {
        "python3".to_string()
    };

    let config = serde_json::json!({
        "mcpServers": {
            "unseen-servant": {
                "command": python_path,
                "args": [
                    mcp_server_py.to_string_lossy(),
                    "--sidecar-url",
                    SIDECAR_URL,
                ]
            }
        }
    });

    serde_json::to_string_pretty(&config)
        .map_err(|e| format!("Failed to serialize config: {}", e))
}

// ---------------------------------------------------------------------------
// Sidecar lifecycle
// ---------------------------------------------------------------------------

fn wait_for_sidecar() {
    use std::net::TcpStream;
    use std::time::Duration;

    let addr = "127.0.0.1:8420";
    let timeout = Duration::from_millis(200);

    for attempt in 1..=50 {
        if TcpStream::connect_timeout(&addr.parse().unwrap(), timeout).is_ok() {
            println!("Sidecar ready after {} attempts", attempt);
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    eprintln!("Warning: Sidecar did not become ready within 5 seconds");
}

fn start_sidecar(data_dir: &Path) -> Result<Child, String> {
    // Resolve paths relative to the project root
    let sidecar_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../sidecar");
    let server_py = sidecar_dir.join("server.py");

    if !server_py.exists() {
        return Err(format!("Sidecar not found at: {}", server_py.display()));
    }

    // Look for a .venv inside the sidecar directory first, fall back to system python3
    let venv_python = sidecar_dir.join(".venv/bin/python3");
    let python = if venv_python.exists() {
        venv_python
    } else {
        std::path::PathBuf::from("python3")
    };

    let child = Command::new(&python)
        .arg(&server_py)
        .arg("--port")
        .arg("8420")
        .arg("--data-dir")
        .arg(data_dir.to_string_lossy().as_ref())
        .spawn()
        .map_err(|e| format!("Failed to start sidecar with {}: {}", python.display(), e))?;

    Ok(child)
}

fn stop_sidecar(state: &SidecarState) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(ref mut child) = *guard {
            // Send SIGTERM for graceful uvicorn shutdown
            #[cfg(unix)]
            {
                let pid = child.id() as i32;
                unsafe { libc::kill(pid, libc::SIGTERM); }
            }
            #[cfg(not(unix))]
            {
                let _ = child.kill();
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
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![select_folder, list_files, check_sidecar_health, index_files, get_index_status, sync_index, get_stats, get_game_systems, get_known_game_systems, set_game_system, get_mcp_config, get_collections, create_collection, update_collection, delete_collection])
        .setup(|app| {
            // Determine where ChromaDB should store data
            let app_data_dir = app
                .path()
                .app_data_dir()
                .expect("Failed to resolve app data directory");
            std::fs::create_dir_all(&app_data_dir).ok();

            let chroma_dir = app_data_dir.join("chroma_db");

            // Start the Python sidecar
            match start_sidecar(&chroma_dir) {
                Ok(child) => {
                    println!("Sidecar started (PID: {})", child.id());
                    app.manage(SidecarState(Mutex::new(Some(child))));
                    wait_for_sidecar();
                }
                Err(e) => {
                    eprintln!("Warning: Could not start sidecar: {}", e);
                    eprintln!("Indexing features will be unavailable.");
                    app.manage(SidecarState(Mutex::new(None)));
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
                .tooltip("Unseen Server")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
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
                    }
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
                    if let Some(window) = app_handle.get_webview_window(&label) {
                        let _ = window.hide();
                    }
                }
                tauri::RunEvent::ExitRequested { api, code, .. } => {
                    if code.is_some() {
                        // Triggered by app.exit() (tray Quit or Cmd+Q) — let it proceed
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

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tauri::Manager;
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
async fn sync_index(paths: Vec<String>) -> Result<SyncResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/sync-index", SIDECAR_URL))
        .json(&serde_json::json!({ "selected_paths": paths }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: SyncResult = response
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
            let _ = child.kill();
            let _ = child.wait();
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
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![select_folder, list_files, index_files, get_index_status, sync_index, get_mcp_config])
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
                }
                Err(e) => {
                    eprintln!("Warning: Could not start sidecar: {}", e);
                    eprintln!("Indexing features will be unavailable.");
                    app.manage(SidecarState(Mutex::new(None)));
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                let state = app_handle.state::<SidecarState>();
                stop_sidecar(state.inner());
                println!("Sidecar stopped.");
            }
        });
}

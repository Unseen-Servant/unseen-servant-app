use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::process::{Child, Command};
use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::Mutex;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager};

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

#[derive(Serialize, Deserialize, Debug, Clone)]
struct FileItem {
    name: String,
    path: String,
    is_dir: bool,
    children: Option<Vec<FileItem>>,
}

#[derive(Serialize, Deserialize, Debug)]
struct FileStatusEntry {
    path: String,
    filename: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    chunk_count: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    game_system: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    game_systems: Option<Vec<String>>,
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
    auto_remove: u32,
    rename: u32,
    update: u32,
    up_to_date: u32,
    errors: u32,
    stale: u32,
    #[serde(default)]
    outdated: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct RenameEntry {
    old_path: String,
    new_path: String,
    filename: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct RenameMapping {
    old_path: String,
    new_path: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct IndexStatusResult {
    to_add: Vec<FileStatusEntry>,
    to_remove: Vec<FileStatusEntry>,
    to_auto_remove: Vec<FileStatusEntry>,
    to_rename: Vec<RenameEntry>,
    to_update: Vec<FileStatusEntry>,
    up_to_date: Vec<FileStatusEntry>,
    errors: Vec<FileErrorEntry>,
    stale_paths: Vec<String>,
    #[serde(default)]
    outdated: Vec<String>,
    summary: IndexStatusSummary,
}

#[derive(Serialize, Deserialize, Debug)]
struct SyncResult {
    added: u32,
    removed: u32,
    auto_removed: u32,
    renamed: u32,
    updated: u32,
    errors: Vec<String>,
    total_indexed: u32,
    chunks_total: u32,
    renames: Vec<RenameMapping>,
    auto_removed_paths: Vec<String>,
    stale_paths: Vec<String>,
}

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

#[derive(Serialize, Clone, Debug)]
struct SyncProgressPayload {
    files_done: u32,
    total_files: u32,
    chunks_total: u32,
    current_file: String,
    phase: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct SetGameSystemResult {
    filename: String,
    game_system: String,
    #[serde(default)]
    game_systems: Vec<String>,
    chunks_updated: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct KnownGameSystem {
    tag: String,
    #[serde(default)]
    keywords: Vec<String>,
    #[serde(default)]
    color: Option<String>,
    #[serde(default)]
    is_builtin: bool,
    #[serde(default)]
    is_customized: bool,
}

#[derive(Serialize, Deserialize, Debug)]
struct KnownGameSystemsResult {
    systems: Vec<KnownGameSystem>,
}

#[derive(Serialize, Deserialize, Debug)]
struct CustomGameSystemResult {
    tag: String,
    keywords: Vec<String>,
    #[serde(default)]
    color: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct ToggleBuiltinResult {
    tag: String,
    disabled: bool,
}

#[derive(Serialize, Deserialize, Debug)]
struct DeleteCustomSystemResult {
    deleted: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct CollectionInfo {
    id: String,
    name: String,
    file_paths: Vec<String>,
    file_count: u32,
    created_at: String,
    updated_at: String,
    last_used_at: Option<String>,
    description: String,
    color: Option<String>,
    archived: bool,
}

/// BTreeMap, not HashMap: this map is re-serialized straight back to the
/// frontend, and HashMap's per-instance random seed would hand JS a
/// differently-ordered object on every get_collections call. Anything
/// rendering `Object.values(collections)` without sorting first would then
/// reshuffle on every refresh. BTreeMap costs nothing here and makes the
/// IPC payload deterministic (by collection name).
#[derive(Serialize, Deserialize, Debug)]
struct CollectionsResult {
    collections: std::collections::BTreeMap<String, CollectionInfo>,
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
    reclaimable_bytes: u64,
}

#[derive(Serialize, Deserialize, Debug)]
struct ReindexFileResult {
    chunks: u32,
    game_system: String,
    error: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct DocumentStats {
    filename: String,
    source: String,
    chunks: u32,
    game_system: String,
    #[serde(default)]
    game_systems: Vec<String>,
    pages: u32,
    indexed_at: Option<String>,
    file_size_bytes: Option<u64>,
}

#[derive(Serialize, Deserialize, Debug)]
struct SourcesResult {
    sources: Vec<DocumentStats>,
    count: u32,
}

#[derive(Serialize, Deserialize, Debug)]
struct CompactResult {
    size_before: u64,
    size_after: u64,
    reclaimed: u64,
}

#[derive(Serialize, Deserialize, Debug)]
struct DeleteIndexResult {
    removed_files: u64,
    removed_chunks: u64,
}

/// A cross-edition twin folded into another result (roadmap 2.3): the
/// same section printed in a different book.
#[derive(Serialize, Deserialize, Debug)]
struct AlsoIn {
    filename: String,
    source: String,
    page_start: u32,
    page_end: u32,
    #[serde(default)]
    page_label_start: String,
    #[serde(default)]
    page_label_end: String,
    #[serde(default)]
    section_id: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct SearchResultItem {
    text: String,
    filename: String,
    source: String,
    section_heading: String,
    page_start: u32,
    page_end: u32,
    game_system: String,
    relevance: f64,
    #[serde(default)]
    tier: Option<String>,
    #[serde(default)]
    reranked: Option<bool>,
    // `text` is now the whole assembled section, so the unit that
    // actually matched has to be named separately (roadmap 2.5). All of
    // these default so an older sidecar still deserializes; the frontend
    // always sees them, blank or empty.
    #[serde(default)]
    matched_text: String,
    #[serde(default)]
    chunk_text: String,
    #[serde(default)]
    section_id: String,
    #[serde(default)]
    section_path: String,
    /// The page numbers printed on the paper. Blank means "cite the
    /// physical span" — the label would mislabel a wider section.
    #[serde(default)]
    page_label_start: String,
    #[serde(default)]
    page_label_end: String,
    /// True when a context budget cut this result back to its matched unit.
    #[serde(default)]
    truncated: bool,
    #[serde(default)]
    also_in: Vec<AlsoIn>,
}

#[derive(Serialize, Deserialize, Debug)]
struct SearchResponse {
    #[serde(default)]
    results: Vec<SearchResultItem>,
    #[serde(default)]
    message: Option<String>,
    /// True when the sidecar's candidate pool ran dry before it had
    /// `n_results` distinct sections — the frontend's end-of-list signal.
    /// Defaults to false so an older sidecar just keeps paging.
    #[serde(default)]
    exhausted: bool,
}

// ---------------------------------------------------------------------------
// Tauri commands — file system
// ---------------------------------------------------------------------------

#[tauri::command]
async fn select_folder(app: tauri::AppHandle) -> Result<String, String> {
    use tauri_plugin_dialog::DialogExt;

    let folder = app
        .dialog()
        .file()
        .set_title("Select your TTRPG folder")
        .blocking_pick_folder();

    match folder {
        Some(path) => Ok(path.to_string()),
        None => Err("No folder selected".to_string()),
    }
}

fn count_pdfs_in_dir(folder: &Path) -> u64 {
    let mut count: u64 = 0;
    let entries = match fs::read_dir(folder) {
        Ok(e) => e,
        Err(_) => return 0,
    };
    for entry in entries.flatten() {
        let file_type = match entry.file_type() {
            Ok(t) => t,
            Err(_) => continue,
        };
        if file_type.is_dir() {
            count += count_pdfs_in_dir(&entry.path());
        } else if file_type.is_file() {
            let name = entry.file_name().to_string_lossy().to_lowercase();
            if name.ends_with(".pdf") {
                count += 1;
            }
        }
    }
    count
}

#[tauri::command]
fn count_pdfs_recursive(folder_path: String) -> Result<u64, String> {
    let folder = Path::new(&folder_path);
    if !folder.is_dir() {
        return Err("Path is not a directory".to_string());
    }
    Ok(count_pdfs_in_dir(folder))
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
        b.is_dir
            .cmp(&a.is_dir)
            .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
    });

    Ok(items)
}

// ---------------------------------------------------------------------------
// Tauri commands — indexing (calls the Python sidecar via HTTP)
// ---------------------------------------------------------------------------

/// Port the sidecar bound at startup, published via ``data_dir/sidecar.port``.
/// Zero means the sidecar has not come up yet — every command that calls it
/// will fail-fast with a connection error in that case, which is the same
/// outcome as a sidecar crash mid-session.
static SIDECAR_PORT: AtomicU16 = AtomicU16::new(0);

fn sidecar_url() -> String {
    format!("http://127.0.0.1:{}", SIDECAR_PORT.load(Ordering::Relaxed))
}

const OLLAMA_URL: &str = "http://localhost:11434";

#[derive(Serialize, Deserialize, Debug)]
struct OllamaStatus {
    running: bool,
    has_model: bool,
}

#[derive(Deserialize, Debug)]
struct OllamaModel {
    name: String,
}

#[derive(Deserialize, Debug)]
struct OllamaTagsResponse {
    models: Vec<OllamaModel>,
}

#[tauri::command]
async fn check_ollama_health() -> Result<OllamaStatus, String> {
    let client = reqwest::Client::new();
    match client
        .get(format!("{}/api/tags", OLLAMA_URL))
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => {
            let tags: OllamaTagsResponse = resp
                .json()
                .await
                .unwrap_or(OllamaTagsResponse { models: vec![] });
            let has_model = tags.models.iter().any(|m| m.name.starts_with("bge-m3"));
            Ok(OllamaStatus {
                running: true,
                has_model,
            })
        }
        _ => Ok(OllamaStatus {
            running: false,
            has_model: false,
        }),
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
async fn get_index_status(paths: Vec<String>) -> Result<IndexStatusResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/index-status", sidecar_url()))
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

async fn consume_sync_stream(
    app: tauri::AppHandle,
    response: reqwest::Response,
) -> Result<SyncResult, String> {
    use futures_util::StreamExt;

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
                                total_files: json["total_files"].as_u64().unwrap_or(0) as u32,
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
                                "auto_removed": json["auto_removed"],
                                "renamed": json["renamed"],
                                "updated": json["updated"],
                                "errors": json["errors"],
                                "total_indexed": json["total_indexed"],
                                "chunks_total": json["chunks_total"],
                                "renames": json["renames"],
                                "auto_removed_paths": json["auto_removed_paths"],
                                "stale_paths": json["stale_paths"],
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

#[tauri::command]
async fn sync_index(app: tauri::AppHandle, paths: Vec<String>) -> Result<SyncResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/sync-index-stream", sidecar_url()))
        .json(&serde_json::json!({ "selected_paths": paths }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if response.status() == reqwest::StatusCode::CONFLICT {
        return Err("sync-busy: a sync is already in progress".to_string());
    }
    consume_sync_stream(app, response).await
}

#[tauri::command]
async fn reindex_all(app: tauri::AppHandle) -> Result<SyncResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/reindex-all-stream", sidecar_url()))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if response.status() == reqwest::StatusCode::CONFLICT {
        return Err("sync-busy: a sync is already in progress".to_string());
    }
    consume_sync_stream(app, response).await
}

#[tauri::command]
async fn reindex_file(path: String) -> Result<ReindexFileResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/reindex-file", sidecar_url()))
        .json(&serde_json::json!({ "path": path }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))
}

#[tauri::command]
async fn get_document_stats(path: String) -> Result<DocumentStats, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/sources", sidecar_url()))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: SourcesResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    result
        .sources
        .into_iter()
        .find(|s| s.source == path)
        .ok_or_else(|| format!("File is not indexed: {}", path))
}

// ---------------------------------------------------------------------------
// Tauri commands — game system management
// ---------------------------------------------------------------------------

#[tauri::command]
async fn get_known_game_systems() -> Result<KnownGameSystemsResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/known-game-systems", sidecar_url()))
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
        .get(format!("{}/api/stats", sidecar_url()))
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
async fn compact_database() -> Result<CompactResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/compact", sidecar_url()))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: CompactResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
fn get_data_dir(app: tauri::AppHandle) -> Result<String, String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("Failed to resolve app data directory: {}", e))?;
    Ok(dir.to_string_lossy().into_owned())
}

#[tauri::command]
async fn delete_index() -> Result<DeleteIndexResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/delete-index", sidecar_url()))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: DeleteIndexResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn set_game_system(
    filename: String,
    game_system: String,
) -> Result<SetGameSystemResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/set-game-system", sidecar_url()))
        .json(&serde_json::json!({
            "filename": filename,
            "game_system": game_system,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: SetGameSystemResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn set_game_systems(
    filename: String,
    game_systems: Vec<String>,
) -> Result<SetGameSystemResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/set-game-systems", sidecar_url()))
        .json(&serde_json::json!({
            "filename": filename,
            "game_systems": game_systems,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: SetGameSystemResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

// ---------------------------------------------------------------------------
// Tauri commands — custom game systems
// ---------------------------------------------------------------------------

#[tauri::command]
async fn create_custom_game_system(
    tag: String,
    keywords: Vec<String>,
    color: Option<String>,
) -> Result<CustomGameSystemResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/custom-game-systems", sidecar_url()))
        .json(&serde_json::json!({
            "tag": tag,
            "keywords": keywords,
            "color": color,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: CustomGameSystemResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn update_custom_game_system(
    original_tag: String,
    tag: String,
    keywords: Vec<String>,
    color: Option<String>,
) -> Result<CustomGameSystemResult, String> {
    let client = reqwest::Client::new();
    let encoded_tag = original_tag.replace("&", "%26").replace(" ", "%20");
    let response = client
        .put(format!(
            "{}/api/custom-game-systems/{}",
            sidecar_url(),
            encoded_tag
        ))
        .json(&serde_json::json!({
            "tag": tag,
            "keywords": keywords,
            "color": color,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: CustomGameSystemResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn delete_custom_game_system(tag: String) -> Result<DeleteCustomSystemResult, String> {
    let client = reqwest::Client::new();
    let encoded_tag = tag.replace("&", "%26").replace(" ", "%20");
    let response = client
        .delete(format!(
            "{}/api/custom-game-systems/{}",
            sidecar_url(),
            encoded_tag
        ))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: DeleteCustomSystemResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn toggle_builtin_game_system(
    tag: String,
    disabled: bool,
) -> Result<ToggleBuiltinResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!(
            "{}/api/custom-game-systems/toggle-builtin",
            sidecar_url()
        ))
        .json(&serde_json::json!({
            "tag": tag,
            "disabled": disabled,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Sidecar error ({}): {}", status, body));
    }

    let result: ToggleBuiltinResult = response
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
        .get(format!("{}/api/collections", sidecar_url()))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let result: CollectionsResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

// The arguments are the IPC contract with the frontend — each one is a
// named key in the `invoke` payload, so they can't be folded into a
// struct without changing every caller.
#[allow(clippy::too_many_arguments)]
#[tauri::command]
async fn search_index(
    query: String,
    n_results: Option<u32>,
    source_filter: Option<String>,
    game_system: Option<String>,
    game_systems: Option<Vec<String>>,
    collection: Option<String>,
    source_paths: Option<Vec<String>>,
    // Character budget for the sidecar's own section packing. The app
    // passes nothing — the inspector wants whole sections — but agentic
    // callers going through the same command can cap the payload.
    max_context_chars: Option<u32>,
) -> Result<SearchResponse, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/search", sidecar_url()))
        .json(&serde_json::json!({
            "query": query,
            "n_results": n_results.unwrap_or(10),
            "source_filter": source_filter,
            "game_system": game_system,
            "game_systems": game_systems,
            "collection": collection,
            "source_paths": source_paths,
            "max_context_chars": max_context_chars,
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!("Search failed ({}): {}", status, body));
    }

    let result: SearchResponse = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
async fn get_search_settings() -> Result<serde_json::Value, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/search-settings", sidecar_url()))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!(
            "Loading search settings failed ({}): {}",
            status, body
        ));
    }

    response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))
}

#[tauri::command]
async fn update_search_settings(partial: serde_json::Value) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::new();
    let response = client
        .put(format!("{}/api/search-settings", sidecar_url()))
        .json(&partial)
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(format!(
            "Saving search settings failed ({}): {}",
            status, body
        ));
    }

    response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))
}

#[tauri::command]
async fn create_collection(
    name: String,
    file_paths: Vec<String>,
    description: String,
    color: Option<String>,
) -> Result<CollectionMutationResult, String> {
    let client = reqwest::Client::new();
    let mut body = serde_json::json!({
        "name": name,
        "file_paths": file_paths,
        "description": description,
    });
    if let Some(c) = color {
        body["color"] = serde_json::Value::String(c);
    }
    let response = client
        .post(format!("{}/api/collections", sidecar_url()))
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
async fn update_collection(
    name: String,
    file_paths: Option<Vec<String>>,
    description: Option<String>,
    color: Option<String>,
    archived: Option<bool>,
) -> Result<CollectionMutationResult, String> {
    let client = reqwest::Client::new();
    let mut body = serde_json::Map::new();
    if let Some(paths) = file_paths {
        body.insert("file_paths".to_string(), serde_json::json!(paths));
    }
    if let Some(desc) = description {
        body.insert("description".to_string(), serde_json::Value::String(desc));
    }
    if let Some(col) = color {
        body.insert("color".to_string(), serde_json::Value::String(col));
    }
    if let Some(a) = archived {
        body.insert("archived".to_string(), serde_json::Value::Bool(a));
    }

    let response = client
        .put(format!("{}/api/collections/{}", sidecar_url(), name))
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
async fn rename_collection(
    name: String,
    new_name: String,
) -> Result<CollectionMutationResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/collections/{}/rename", sidecar_url(), name))
        .json(&serde_json::json!({ "new_name": new_name }))
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
        .delete(format!("{}/api/collections/{}", sidecar_url(), name))
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
// Tauri commands — file management
// ---------------------------------------------------------------------------

/// Reject names that could escape the parent directory or violate filesystem
/// constraints on macOS or Windows. Path-traversal defense (`..`, separators,
/// null bytes) is the primary purpose; the rest catches names that would
/// behave unexpectedly on Windows.
fn validate_rename_name(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("Name cannot be empty".to_string());
    }
    if name.contains('/') || name.contains('\\') {
        return Err("Name cannot contain '/' or '\\'".to_string());
    }
    if name.contains('\0') {
        return Err("Name contains an invalid character".to_string());
    }
    if name == "." || name == ".." {
        return Err("Name cannot be '.' or '..'".to_string());
    }
    if name.chars().any(|c| (c as u32) < 0x20 || c == '\u{7F}') {
        return Err("Name contains a control character".to_string());
    }
    if name.ends_with('.') || name.ends_with(' ') {
        return Err("Name cannot end with a period or space".to_string());
    }
    let stem = name.split('.').next().unwrap_or(name).to_ascii_uppercase();
    const WIN_RESERVED: &[&str] = &[
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
        "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    ];
    if WIN_RESERVED.iter().any(|r| *r == stem) {
        return Err(format!("'{}' is a reserved name on Windows", name));
    }
    Ok(())
}

#[tauri::command]
async fn rename_file(old_path: String, new_name: String) -> Result<String, String> {
    validate_rename_name(&new_name)?;
    let old = Path::new(&old_path);
    if !old.exists() {
        return Err("File not found".to_string());
    }
    let parent = old
        .parent()
        .ok_or("Cannot determine parent directory".to_string())?;
    let new_path = parent.join(&new_name);
    // Defense in depth: confirm new_path stays in the original parent.
    if new_path.parent() != Some(parent) {
        return Err("Name escapes parent directory".to_string());
    }
    if new_path.exists() {
        return Err(format!("A file named '{}' already exists", new_name));
    }
    fs::rename(old, &new_path).map_err(|e| e.to_string())?;

    let new_path_str = new_path.to_string_lossy().into_owned();

    // Best-effort sidecar update — if it fails, the next auto-sync will handle it
    let client = reqwest::Client::new();
    let _ = client
        .post(format!("{}/api/file-rename", sidecar_url()))
        .json(&serde_json::json!({
            "old_path": old_path,
            "new_path": new_path_str,
        }))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    Ok(new_path_str)
}

#[tauri::command]
async fn delete_file(path: String) -> Result<(), String> {
    let p = Path::new(&path);
    if !p.exists() {
        return Err("File not found".to_string());
    }
    trash::delete(p).map_err(|e| format!("Failed to move to trash: {}", e))?;

    // Best-effort sidecar update — if it fails, the next auto-sync will handle it
    let client = reqwest::Client::new();
    let _ = client
        .post(format!("{}/api/file-delete", sidecar_url()))
        .json(&serde_json::json!({
            "path": path,
        }))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    Ok(())
}

#[tauri::command]
async fn rename_folder(old_path: String, new_name: String) -> Result<String, String> {
    validate_rename_name(&new_name)?;
    let old = Path::new(&old_path);
    if !old.exists() || !old.is_dir() {
        return Err("Folder not found".to_string());
    }
    let parent = old
        .parent()
        .ok_or("Cannot determine parent directory".to_string())?;
    let new_path = parent.join(&new_name);
    if new_path.parent() != Some(parent) {
        return Err("Name escapes parent directory".to_string());
    }
    if new_path.exists() {
        return Err(format!("A folder named '{}' already exists", new_name));
    }
    fs::rename(old, &new_path).map_err(|e| e.to_string())?;

    let new_path_str = new_path.to_string_lossy().into_owned();

    // Best-effort sidecar update — if it fails, the next auto-sync will handle it
    let client = reqwest::Client::new();
    let _ = client
        .post(format!("{}/api/folder-rename", sidecar_url()))
        .json(&serde_json::json!({
            "old_prefix": old_path,
            "new_prefix": new_path_str,
        }))
        .timeout(std::time::Duration::from_secs(30))
        .send()
        .await;

    Ok(new_path_str)
}

#[tauri::command]
async fn delete_folder(path: String) -> Result<(), String> {
    let p = Path::new(&path);
    if !p.exists() || !p.is_dir() {
        return Err("Folder not found".to_string());
    }
    trash::delete(p).map_err(|e| format!("Failed to move to trash: {}", e))?;

    // Best-effort sidecar update — if it fails, the next auto-sync will handle it
    let client = reqwest::Client::new();
    let _ = client
        .post(format!("{}/api/folder-delete", sidecar_url()))
        .json(&serde_json::json!({
            "folder_prefix": path,
        }))
        .timeout(std::time::Duration::from_secs(30))
        .send()
        .await;

    Ok(())
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
            select_folder,
            list_files,
            count_pdfs_recursive,
            rename_file,
            delete_file,
            rename_folder,
            delete_folder,
            check_ollama_health,
            check_sidecar_health,
            check_mcp_status,
            get_index_status,
            sync_index,
            reindex_all,
            reindex_file,
            get_document_stats,
            get_stats,
            compact_database,
            delete_index,
            get_data_dir,
            get_known_game_systems,
            set_game_system,
            set_game_systems,
            create_custom_game_system,
            update_custom_game_system,
            delete_custom_game_system,
            toggle_builtin_game_system,
            get_mcp_config,
            get_collections,
            create_collection,
            update_collection,
            rename_collection,
            delete_collection,
            get_sidecar_failure,
            search_index,
            get_search_settings,
            update_search_settings
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
    fn validate_rename_name_accepts_normal_names() {
        assert!(validate_rename_name("Curse of Strahd.pdf").is_ok());
        assert!(validate_rename_name("My Campaign").is_ok());
        assert!(validate_rename_name("file_with-dashes.pdf").is_ok());
        assert!(validate_rename_name("résumé.pdf").is_ok());
    }

    #[test]
    fn validate_rename_name_rejects_path_traversal() {
        assert!(validate_rename_name("..").is_err());
        assert!(validate_rename_name(".").is_err());
        assert!(validate_rename_name("../evil").is_err());
        assert!(validate_rename_name("..\\evil").is_err());
        assert!(validate_rename_name("foo/bar").is_err());
        assert!(validate_rename_name("foo\\bar").is_err());
    }

    #[test]
    fn validate_rename_name_rejects_null_byte() {
        assert!(validate_rename_name("foo\0bar").is_err());
    }

    #[test]
    fn validate_rename_name_rejects_empty() {
        assert!(validate_rename_name("").is_err());
    }

    #[test]
    fn validate_rename_name_rejects_control_chars() {
        assert!(validate_rename_name("foo\nbar").is_err());
        assert!(validate_rename_name("foo\tbar").is_err());
        assert!(validate_rename_name("foo\x7fbar").is_err());
    }

    #[test]
    fn validate_rename_name_rejects_windows_reserved() {
        assert!(validate_rename_name("CON").is_err());
        assert!(validate_rename_name("con").is_err());
        assert!(validate_rename_name("NUL.pdf").is_err());
        assert!(validate_rename_name("COM1.txt").is_err());
        assert!(validate_rename_name("LPT9").is_err());
    }

    #[test]
    fn validate_rename_name_rejects_trailing_dot_or_space() {
        assert!(validate_rename_name("foo.").is_err());
        assert!(validate_rename_name("foo ").is_err());
    }

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

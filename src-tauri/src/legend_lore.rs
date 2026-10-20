//! Legend Lore — the library browser and the Tauri commands that proxy
//! its indexing, search, collection and game-system requests to the
//! Python sidecar. The sidecar lifecycle, tray and windows stay in lib.rs.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tauri::Emitter;

use super::sidecar_url;
use crate::sse::SseFrames;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FileItem {
    name: String,
    path: String,
    is_dir: bool,
    /// A picture in the library (images design §6): listed beside the books
    /// for Send to Command, never indexed.
    #[serde(default)]
    is_image: bool,
    children: Option<Vec<FileItem>>,
}

/// What the tree lists as a picture: the image types Command takes.
const IMAGE_EXTENSIONS: [&str; 6] = ["png", "jpg", "jpeg", "gif", "webp", "svg"];

pub(crate) fn is_image_name(name: &str) -> bool {
    !name.starts_with('.')
        && Path::new(name)
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| IMAGE_EXTENSIONS.contains(&e.to_lowercase().as_str()))
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
pub struct IndexStatusResult {
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
pub struct SyncResult {
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
    #[serde(default)]
    unindexable_paths: Vec<String>,
}

#[derive(Serialize, Clone, Debug)]
struct SyncProgressPayload {
    files_done: u32,
    total_files: u32,
    chunks_total: u32,
    current_file: String,
    phase: String,
    // How far into the current book's embedding; 0/0 outside it.
    book_chunks_done: u32,
    book_chunks_total: u32,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct SetGameSystemResult {
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
pub struct KnownGameSystemsResult {
    systems: Vec<KnownGameSystem>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct CustomGameSystemResult {
    tag: String,
    keywords: Vec<String>,
    #[serde(default)]
    color: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ToggleBuiltinResult {
    tag: String,
    disabled: bool,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct DeleteCustomSystemResult {
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
pub struct CollectionsResult {
    collections: std::collections::BTreeMap<String, CollectionInfo>,
    count: u32,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct CollectionMutationResult {
    name: String,
    file_count: u32,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct CollectionDeleteResult {
    message: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct StatsResult {
    total_chunks: u32,
    total_documents: u32,
    storage_bytes: u64,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ReindexFileResult {
    chunks: u32,
    game_system: String,
    error: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct DocumentStats {
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
pub struct DeleteIndexResult {
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
pub struct SearchResponse {
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

/// A tree path as the UI and sidecar spell it: '/' separators on every
/// platform. Both split and prefix-match on '/', and Windows APIs accept
/// '/' as well as '\'. Only Windows is rewritten — '\' is a legal
/// filename character on macOS and Linux.
fn ui_path_string(raw: &str, windows: bool) -> String {
    if windows {
        raw.replace('\\', "/")
    } else {
        raw.to_string()
    }
}

fn ui_path(path: &Path) -> String {
    ui_path_string(&path.to_string_lossy(), cfg!(windows))
}

/// The folder picked, or None when the dialog was cancelled: a cancel is
/// not an error.
#[tauri::command]
pub async fn select_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;

    let folder = app
        .dialog()
        .file()
        .set_title("Select your TTRPG folder")
        .blocking_pick_folder();

    Ok(folder.map(|path| ui_path_string(&path.to_string(), cfg!(windows))))
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
pub fn count_pdfs_recursive(folder_path: String) -> Result<u64, String> {
    let folder = Path::new(&folder_path);
    if !folder.is_dir() {
        return Err("Path is not a directory".to_string());
    }
    Ok(count_pdfs_in_dir(folder))
}

#[tauri::command]
pub fn list_files(folder_path: String) -> Result<Vec<FileItem>, String> {
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
        let path = ui_path(&folder.join(&name));
        let is_pdf = !is_dir && name.to_lowercase().ends_with(".pdf");
        let is_image = !is_dir && is_image_name(&name);

        if is_dir || is_pdf || is_image {
            items.push(FileItem {
                name,
                path,
                is_dir,
                is_image,
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

/// `list_files` all the way down: every folder carries its children. The
/// search bar's `/` filter needs names inside folders nobody has opened.
/// Symlinked folders aren't followed (`list_files` doesn't list them as
/// folders), so the walk can't loop.
#[tauri::command]
pub fn list_tree(folder_path: String) -> Result<Vec<FileItem>, String> {
    let mut items = list_files(folder_path)?;
    for item in items.iter_mut().filter(|i| i.is_dir) {
        item.children = Some(list_tree(item.path.clone()).unwrap_or_default());
    }
    Ok(items)
}

// ---------------------------------------------------------------------------
// Tauri commands — indexing (calls the Python sidecar via HTTP)
// ---------------------------------------------------------------------------

#[tauri::command]
pub async fn get_index_status(paths: Vec<String>) -> Result<IndexStatusResult, String> {
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

/// The error for a sync-stream request the sidecar refused. 409 keeps the
/// `sync-busy:` prefix syncJob.ts matches on; anything else carries the
/// sidecar's own message rather than reaching the stream parser, which
/// would report it as a sync that finished without a result.
fn sync_refusal(status: reqwest::StatusCode, body: &str) -> String {
    if status == reqwest::StatusCode::CONFLICT {
        "sync-busy: a sync is already in progress".to_string()
    } else {
        format!("Sidecar error ({}): {}", status, body)
    }
}

#[derive(Debug)]
enum SyncEvent {
    Progress(SyncProgressPayload),
    Complete(SyncResult),
}

/// What one sync-stream frame means to the app: progress to relay, the
/// final result (failures reach the UI through its `errors`), or nothing
/// for an event this build doesn't know. A `complete` that doesn't
/// deserialize is an error, not a sync that ended without a result.
fn sync_event(json: &serde_json::Value) -> Result<Option<SyncEvent>, String> {
    let count = |key: &str| json[key].as_u64().unwrap_or(0) as u32;
    let text = |key: &str| json[key].as_str().unwrap_or("").to_string();
    match json.get("event").and_then(|e| e.as_str()) {
        Some("started") => Ok(Some(SyncEvent::Progress(SyncProgressPayload {
            files_done: 0,
            total_files: count("total_files"),
            chunks_total: 0,
            current_file: String::new(),
            phase: String::new(),
            book_chunks_done: 0,
            book_chunks_total: 0,
        }))),
        Some("progress") => Ok(Some(SyncEvent::Progress(SyncProgressPayload {
            files_done: count("files_done"),
            total_files: count("total_files"),
            chunks_total: count("chunks_total"),
            current_file: text("current_file"),
            phase: text("phase"),
            book_chunks_done: count("book_chunks_done"),
            book_chunks_total: count("book_chunks_total"),
        }))),
        Some("complete") => serde_json::from_value(json.clone())
            .map(|r| Some(SyncEvent::Complete(r)))
            .map_err(|e| format!("Invalid sync result: {}", e)),
        _ => Ok(None),
    }
}

async fn consume_sync_stream(
    app: tauri::AppHandle,
    response: reqwest::Response,
) -> Result<SyncResult, String> {
    use futures_util::StreamExt;

    let mut stream = response.bytes_stream();
    let mut frames = SseFrames::default();
    let mut final_result: Option<SyncResult> = None;

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("Stream error: {}", e))?;
        for json in frames.push(&chunk) {
            match sync_event(&json)? {
                Some(SyncEvent::Progress(payload)) => {
                    let _ = app.emit("sync-progress", &payload);
                }
                Some(SyncEvent::Complete(result)) => final_result = Some(result),
                None => {}
            }
        }
    }

    final_result.ok_or_else(|| "Sync completed but no result received".to_string())
}

#[tauri::command]
pub async fn sync_index(app: tauri::AppHandle, paths: Vec<String>) -> Result<SyncResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/sync-index-stream", sidecar_url()))
        .json(&serde_json::json!({ "selected_paths": paths }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        return Err(sync_refusal(status, &body));
    }
    consume_sync_stream(app, response).await
}

#[tauri::command]
pub async fn reindex_all(app: tauri::AppHandle) -> Result<SyncResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/reindex-all-stream", sidecar_url()))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        return Err(sync_refusal(status, &body));
    }
    consume_sync_stream(app, response).await
}

#[tauri::command]
pub async fn reindex_file(path: String) -> Result<ReindexFileResult, String> {
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
pub async fn get_document_stats(path: String) -> Result<DocumentStats, String> {
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
pub async fn get_known_game_systems() -> Result<KnownGameSystemsResult, String> {
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
pub async fn get_stats() -> Result<StatsResult, String> {
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
pub async fn delete_index() -> Result<DeleteIndexResult, String> {
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
pub async fn set_game_systems(
    path: String,
    game_systems: Vec<String>,
) -> Result<SetGameSystemResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/set-game-systems", sidecar_url()))
        .json(&serde_json::json!({
            "path": path,
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
pub async fn create_custom_game_system(
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
pub async fn update_custom_game_system(
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
pub async fn delete_custom_game_system(tag: String) -> Result<DeleteCustomSystemResult, String> {
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
pub async fn toggle_builtin_game_system(
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
pub async fn get_collections() -> Result<CollectionsResult, String> {
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
pub async fn search_index(
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
    // The query's last word may still be being typed (a debounced search
    // whose text doesn't end in whitespace): the sidecar completes it
    // instead of spell-correcting it and prefix-matches it in BM25.
    partial: Option<bool>,
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
            "partial": partial.unwrap_or(false),
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(sidecar_refusal(status, &body));
    }

    let result: SearchResponse = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
pub async fn get_search_settings() -> Result<serde_json::Value, String> {
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
pub async fn update_search_settings(
    partial: serde_json::Value,
) -> Result<serde_json::Value, String> {
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
pub async fn create_collection(
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

/// A refusal from the sidecar in its own words: FastAPI's `detail` when the
/// body carries one, the status and body otherwise.
fn sidecar_refusal(status: reqwest::StatusCode, body: &str) -> String {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| v.get("detail")?.as_str().map(str::to_string))
        .unwrap_or_else(|| format!("Sidecar error ({}): {}", status, body))
}

/// The sidecar URL for one collection. Its name is the GM's own text, so it
/// goes in percent-encoded as a single path segment: a `?`, `#`, `%` or `/`
/// would otherwise end the path or split it.
fn collection_url(base: &str, name: &str, action: Option<&str>) -> Result<reqwest::Url, String> {
    let mut url = reqwest::Url::parse(base).map_err(|e| e.to_string())?;
    {
        let mut segments = url
            .path_segments_mut()
            .map_err(|_| format!("Not a base URL: {}", base))?;
        segments.pop_if_empty().extend(["api", "collections", name]);
        if let Some(action) = action {
            segments.push(action);
        }
    }
    Ok(url)
}

#[tauri::command]
pub async fn update_collection(
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
        .put(collection_url(&sidecar_url(), &name, None)?)
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
pub async fn rename_collection(
    name: String,
    new_name: String,
) -> Result<CollectionMutationResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(collection_url(&sidecar_url(), &name, Some("rename"))?)
        .json(&serde_json::json!({ "new_name": new_name }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to indexer: {}", e))?;

    // The rename field shows a refusal under itself, so it's the sidecar's
    // sentence, not the HTTP exchange.
    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(sidecar_refusal(status, &body));
    }

    let result: CollectionMutationResult = response
        .json()
        .await
        .map_err(|e| format!("Invalid response from indexer: {}", e))?;

    Ok(result)
}

#[tauri::command]
pub async fn delete_collection(name: String) -> Result<CollectionDeleteResult, String> {
    let client = reqwest::Client::new();
    let response = client
        .delete(collection_url(&sidecar_url(), &name, None)?)
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

/// Whether renaming `old` to `new_path` would land on another entry. On a
/// case-insensitive volume (macOS's default) a change of case alone makes
/// the new spelling "exist" because it is the source itself; the folder's
/// own listing tells that apart from a second entry spelled that way, which
/// only a case-sensitive volume can hold.
fn rename_target_taken(old: &Path, new_path: &Path) -> bool {
    if !new_path.exists() {
        return false;
    }
    let (Some(old_name), Some(new_name), Some(parent)) =
        (old.file_name(), new_path.file_name(), new_path.parent())
    else {
        return true;
    };
    if old_name.to_string_lossy().to_lowercase() != new_name.to_string_lossy().to_lowercase() {
        return true;
    }
    match fs::read_dir(parent) {
        Ok(entries) => entries
            .flatten()
            .any(|e| e.file_name() == new_name && e.file_name() != old_name),
        Err(_) => true,
    }
}

#[tauri::command]
pub async fn rename_file(old_path: String, new_name: String) -> Result<String, String> {
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
    if rename_target_taken(old, &new_path) {
        return Err(format!("A file named '{}' already exists", new_name));
    }
    fs::rename(old, &new_path).map_err(|e| e.to_string())?;

    let new_path_str = ui_path(&new_path);

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
pub async fn delete_file(path: String) -> Result<(), String> {
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
pub async fn rename_folder(old_path: String, new_name: String) -> Result<String, String> {
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
    if rename_target_taken(old, &new_path) {
        return Err(format!("A folder named '{}' already exists", new_name));
    }
    fs::rename(old, &new_path).map_err(|e| e.to_string())?;

    let new_path_str = ui_path(&new_path);

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
pub async fn delete_folder(path: String) -> Result<(), String> {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ui_path_string_turns_windows_separators_into_slashes() {
        assert_eq!(
            ui_path_string(r"C:\lib\Core\a.pdf", true),
            "C:/lib/Core/a.pdf"
        );
        // Path::join on a '/'-spelled folder gives a mixed path on Windows.
        assert_eq!(
            ui_path_string(r"C:/lib/Core\a.pdf", true),
            "C:/lib/Core/a.pdf"
        );
    }

    #[test]
    fn ui_path_string_leaves_unix_paths_alone() {
        // '\' is a legal filename character on macOS and Linux.
        assert_eq!(
            ui_path_string(r"/lib/odd\name.pdf", false),
            r"/lib/odd\name.pdf"
        );
    }

    /// A fresh directory under the system temp dir, unique to this test.
    fn scratch_dir(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "unseen-servant-test-{}-{}",
            std::process::id(),
            name
        ));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn list_files_puts_folders_first_then_sorts_case_insensitively() {
        let dir = scratch_dir("list-files-order");
        for f in [
            "b.PDF",
            "a.pdf",
            "notes.txt",
            ".DS_Store",
            "Map.JPG",
            ".hidden.png",
        ] {
            fs::write(dir.join(f), b"").unwrap();
        }
        for d in ["Zeta", "alpha"] {
            fs::create_dir(dir.join(d)).unwrap();
        }

        let items = list_files(dir.to_string_lossy().into_owned()).unwrap();

        // Images are listed beside the books, marked; other files and
        // hidden ones aren't.
        let names: Vec<(&str, bool, bool)> = items
            .iter()
            .map(|i| (i.name.as_str(), i.is_dir, i.is_image))
            .collect();
        assert_eq!(
            names,
            vec![
                ("alpha", true, false),
                ("Zeta", true, false),
                ("a.pdf", false, false),
                ("b.PDF", false, false),
                ("Map.JPG", false, true)
            ]
        );
        assert_eq!(items[2].path, ui_path(&dir.join("a.pdf")));
        assert!(items.iter().all(|i| i.children.is_none()));
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn list_files_rejects_a_path_that_is_not_a_directory() {
        let dir = scratch_dir("list-files-not-dir");
        let file = dir.join("a.pdf");
        fs::write(&file, b"").unwrap();

        assert!(list_files(file.to_string_lossy().into_owned()).is_err());
        assert!(list_files(dir.join("missing").to_string_lossy().into_owned()).is_err());
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn list_tree_fills_every_folder_with_its_listing() {
        let dir = scratch_dir("list-tree");
        fs::create_dir_all(dir.join("Core/Deep")).unwrap();
        fs::create_dir(dir.join("Empty")).unwrap();
        for f in ["Core/b.pdf", "Core/Deep/c.PDF", "Core/notes.txt", "a.pdf"] {
            fs::write(dir.join(f), b"").unwrap();
        }

        let items = list_tree(dir.to_string_lossy().into_owned()).unwrap();

        let names: Vec<&str> = items.iter().map(|i| i.name.as_str()).collect();
        assert_eq!(names, vec!["Core", "Empty", "a.pdf"]);
        let core = items[0].children.as_ref().unwrap();
        let core_names: Vec<&str> = core.iter().map(|i| i.name.as_str()).collect();
        assert_eq!(core_names, vec!["Deep", "b.pdf"]);
        let deep = core[0].children.as_ref().unwrap();
        assert_eq!(deep[0].path, ui_path(&dir.join("Core/Deep/c.PDF")));
        assert!(deep[0].children.is_none());
        assert!(items[1].children.as_ref().unwrap().is_empty());
        assert!(items[2].children.is_none());
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn count_pdfs_in_dir_counts_nested_pdfs_in_any_case() {
        let dir = scratch_dir("count-pdfs");
        fs::create_dir_all(dir.join("sub/deeper")).unwrap();
        for f in [
            "a.pdf",
            "sub/b.PDF",
            "sub/deeper/c.Pdf",
            "sub/notes.txt",
            "sub/pdf",
        ] {
            fs::write(dir.join(f), b"").unwrap();
        }

        assert_eq!(count_pdfs_in_dir(&dir), 3);
        assert_eq!(count_pdfs_in_dir(&dir.join("missing")), 0);
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn sync_event_reads_started_and_progress_as_progress() {
        let started = serde_json::json!({"event": "started", "total_files": 12});
        match sync_event(&started) {
            Ok(Some(SyncEvent::Progress(p))) => {
                assert_eq!((p.files_done, p.total_files), (0, 12));
                assert_eq!(p.phase, "");
            }
            other => panic!("expected progress, got {:?}", other),
        }

        let progress = serde_json::json!({
            "event": "progress", "files_done": 3, "total_files": 12,
            "chunks_total": 40, "current_file": "Monster Manual.pdf", "phase": "add",
        });
        match sync_event(&progress) {
            Ok(Some(SyncEvent::Progress(p))) => {
                assert_eq!((p.files_done, p.total_files, p.chunks_total), (3, 12, 40));
                assert_eq!(p.current_file, "Monster Manual.pdf");
                assert_eq!(p.phase, "add");
                assert_eq!((p.book_chunks_done, p.book_chunks_total), (0, 0));
            }
            other => panic!("expected progress, got {:?}", other),
        }
    }

    #[test]
    fn sync_event_reads_complete_as_the_result() {
        let complete = serde_json::json!({
            "event": "complete", "added": 2, "removed": 0, "auto_removed": 0,
            "renamed": 1, "updated": 0, "errors": ["bad.pdf: no text"],
            "total_indexed": 9, "chunks_total": 120,
            "renames": [{"old_path": "/a.pdf", "new_path": "/b.pdf"}],
            "auto_removed_paths": [], "stale_paths": [],
            "unindexable_paths": ["/bad.pdf"],
        });
        match sync_event(&complete) {
            Ok(Some(SyncEvent::Complete(r))) => {
                assert_eq!((r.added, r.renamed, r.total_indexed), (2, 1, 9));
                assert_eq!(r.errors, vec!["bad.pdf: no text"]);
                assert_eq!(r.unindexable_paths, vec!["/bad.pdf"]);
            }
            other => panic!("expected complete, got {:?}", other),
        }
    }

    #[test]
    fn sync_event_rejects_a_malformed_complete() {
        let complete = serde_json::json!({"event": "complete", "added": "lots"});
        let err = sync_event(&complete).unwrap_err();
        assert!(err.starts_with("Invalid sync result"), "{err}");
    }

    #[test]
    fn sync_event_ignores_unknown_events() {
        let unknown = serde_json::json!({"event": "something-new", "file": "x.pdf"});
        assert!(matches!(sync_event(&unknown), Ok(None)));
    }

    #[test]
    fn sync_refusal_keeps_the_busy_prefix_the_frontend_matches() {
        let msg = sync_refusal(reqwest::StatusCode::CONFLICT, "Sync in progress");
        assert!(msg.starts_with("sync-busy:"), "{msg}");
    }

    #[test]
    fn sync_refusal_surfaces_other_statuses_with_the_sidecar_body() {
        let msg = sync_refusal(
            reqwest::StatusCode::INTERNAL_SERVER_ERROR,
            r#"{"detail":"No data directory configured"}"#,
        );
        assert!(!msg.starts_with("sync-busy:"), "{msg}");
        assert!(msg.contains("500"), "{msg}");
        assert!(msg.contains("No data directory configured"), "{msg}");
    }

    #[test]
    fn a_sidecar_refusal_reads_in_its_own_words() {
        assert_eq!(
            sidecar_refusal(
                reqwest::StatusCode::CONFLICT,
                r#"{"detail":"Collection already exists: Monsters"}"#
            ),
            "Collection already exists: Monsters"
        );
        assert_eq!(
            sidecar_refusal(reqwest::StatusCode::INTERNAL_SERVER_ERROR, "boom"),
            "Sidecar error (500 Internal Server Error): boom"
        );
    }

    #[test]
    fn a_collection_url_keeps_the_name_to_one_path_segment() {
        let base = "http://127.0.0.1:8420";
        assert_eq!(
            collection_url(base, "Monsters", None).unwrap().as_str(),
            "http://127.0.0.1:8420/api/collections/Monsters"
        );
        assert_eq!(
            collection_url(base, "Act 1/Prep? #50%", Some("rename"))
                .unwrap()
                .as_str(),
            "http://127.0.0.1:8420/api/collections/Act%201%2FPrep%3F%20%2350%25/rename"
        );
    }

    #[test]
    fn rename_target_is_free_under_a_new_name() {
        let dir = scratch_dir("rename-free");
        fs::write(dir.join("a.pdf"), b"").unwrap();
        assert!(!rename_target_taken(&dir.join("a.pdf"), &dir.join("b.pdf")));
    }

    #[test]
    fn rename_target_is_taken_by_another_entry() {
        let dir = scratch_dir("rename-taken");
        fs::write(dir.join("a.pdf"), b"").unwrap();
        fs::write(dir.join("b.pdf"), b"").unwrap();
        assert!(rename_target_taken(&dir.join("a.pdf"), &dir.join("b.pdf")));
        fs::create_dir(dir.join("Modules")).unwrap();
        fs::create_dir(dir.join("Adventures")).unwrap();
        assert!(rename_target_taken(
            &dir.join("Modules"),
            &dir.join("Adventures")
        ));
    }

    #[test]
    fn a_change_of_case_alone_renames_the_entry_itself() {
        let dir = scratch_dir("rename-case");
        fs::write(dir.join("players handbook.pdf"), b"").unwrap();
        let old = dir.join("players handbook.pdf");
        let new = dir.join("Players Handbook.pdf");
        // On a case-insensitive volume the new spelling "exists": it's the
        // source itself, so it isn't taken.
        assert!(!rename_target_taken(&old, &new));
        fs::rename(&old, &new).unwrap();
        let names: Vec<String> = fs::read_dir(&dir)
            .unwrap()
            .flatten()
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect();
        assert_eq!(names, vec!["Players Handbook.pdf"]);
    }

    #[test]
    fn a_change_of_case_onto_another_file_is_taken_where_case_matters() {
        let dir = scratch_dir("rename-case-other");
        fs::write(dir.join("a.pdf"), b"").unwrap();
        fs::write(dir.join("A.pdf"), b"").unwrap();
        // Only a case-sensitive volume holds both; on the others the second
        // write landed on the first and there's nothing else to clobber.
        if fs::read_dir(&dir).unwrap().count() == 2 {
            assert!(rename_target_taken(&dir.join("a.pdf"), &dir.join("A.pdf")));
        }
    }

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
}

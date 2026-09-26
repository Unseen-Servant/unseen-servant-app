//! Legend Lore — the library browser and the Tauri commands that proxy
//! its indexing, search, collection and game-system requests to the
//! Python sidecar. The sidecar lifecycle, tray and windows stay in lib.rs.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tauri::Emitter;

use super::sidecar_url;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FileItem {
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
    collection_name: String,
    storage_bytes: u64,
    reclaimable_bytes: u64,
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
pub struct CompactResult {
    size_before: u64,
    size_after: u64,
    reclaimed: u64,
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

#[tauri::command]
pub async fn select_folder(app: tauri::AppHandle) -> Result<String, String> {
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
pub async fn sync_index(app: tauri::AppHandle, paths: Vec<String>) -> Result<SyncResult, String> {
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
pub async fn reindex_all(app: tauri::AppHandle) -> Result<SyncResult, String> {
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
pub async fn compact_database() -> Result<CompactResult, String> {
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
pub async fn rename_collection(
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
pub async fn delete_collection(name: String) -> Result<CollectionDeleteResult, String> {
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

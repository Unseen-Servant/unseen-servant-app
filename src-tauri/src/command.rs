//! Command — Tauri commands over the campaign vault the sidecar keeps
//! (`sidecar/command/`), the relay that carries its change events to every
//! window, and deletion through the OS trash (design doc §6.3).

use reqwest::{RequestBuilder, StatusCode};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tauri::{AppHandle, Emitter};

use crate::sidecar_url;
use crate::sse::SseFrames;

/// Change events for the campaign folder, relayed as the sidecar sends them:
/// `{ type: "vault", campaign, paths }`, where a null campaign means
/// "anything may have changed — refetch everything".
pub const VAULT_EVENT: &str = "command://vault";

/// Generous: a rename rewrites links across every note in the campaign.
const TIMEOUT: Duration = Duration::from_secs(30);
const RETRY_MIN: Duration = Duration::from_secs(1);
const RETRY_MAX: Duration = Duration::from_secs(10);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug)]
pub struct CommandSettings {
    root: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct NoteEntry {
    name: String,
    path: String,
    track: Option<String>,
    group: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct CampaignIndex {
    name: String,
    tracks: Vec<String>,
    notes: Vec<NoteEntry>,
    ambiguous: Vec<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct Note {
    path: String,
    name: String,
    content: String,
    hash: String,
}

/// A renamed campaign or track, and the notes whose links were rewritten.
#[derive(Serialize, Deserialize, Debug)]
pub struct Renamed {
    name: String,
    rewritten: Vec<String>,
}

/// A renamed or moved note's new path, and the notes whose links were rewritten.
#[derive(Serialize, Deserialize, Debug)]
pub struct Moved {
    path: String,
    rewritten: Vec<String>,
}

/// A save is either written or refused because the file changed on disk
/// since it was loaded. The refusal isn't an error: the editor shows it and
/// the GM chooses, so it carries the hash now on disk for a deliberate retry.
#[derive(Serialize, Debug, PartialEq)]
#[serde(tag = "status", rename_all = "lowercase")]
pub enum SaveOutcome {
    Saved { hash: String },
    Conflict { hash: String },
}

#[derive(Deserialize)]
struct Named {
    name: String,
}

#[derive(Deserialize)]
struct AtPath {
    path: String,
}

#[derive(Deserialize)]
struct Hashed {
    hash: String,
}

// ---------------------------------------------------------------------------
// Talking to the sidecar
// ---------------------------------------------------------------------------

fn api(path: &str) -> String {
    format!("{}/api/command{}", sidecar_url(), path)
}

/// A GET route with its query string encoded (names carry spaces and accents).
fn api_query(path: &str, params: &[(&str, &str)]) -> Result<reqwest::Url, String> {
    reqwest::Url::parse_with_params(&api(path), params).map_err(|e| e.to_string())
}

fn client() -> reqwest::Client {
    reqwest::Client::new()
}

/// What to tell the GM when the sidecar refuses: its own `detail` message
/// ("A note named 'Ismark' already exists…") when there is one.
fn refusal(status: StatusCode, body: &str) -> String {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| v.get("detail")?.as_str().map(str::to_string))
        .unwrap_or_else(|| format!("Sidecar error ({}): {}", status, body))
}

async fn answer<T: DeserializeOwned>(request: RequestBuilder) -> Result<T, String> {
    let response = request
        .timeout(TIMEOUT)
        .send()
        .await
        .map_err(|e| format!("Failed to connect to the sidecar: {}", e))?;
    let status = response.status();
    if status.is_success() {
        response
            .json()
            .await
            .map_err(|e| format!("Invalid response from the sidecar: {}", e))
    } else {
        let body = response.text().await.unwrap_or_default();
        Err(refusal(status, &body))
    }
}

fn save_outcome(status: StatusCode, body: &str) -> Result<SaveOutcome, String> {
    let hashed = || serde_json::from_str::<Hashed>(body).map(|h| h.hash);
    if status.is_success() {
        hashed()
            .map(|hash| SaveOutcome::Saved { hash })
            .map_err(|e| format!("Invalid response from the sidecar: {}", e))
    } else if status == StatusCode::CONFLICT {
        hashed()
            .map(|hash| SaveOutcome::Conflict { hash })
            .map_err(|_| refusal(status, body))
    } else {
        Err(refusal(status, body))
    }
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[tauri::command]
pub async fn command_get_settings() -> Result<CommandSettings, String> {
    answer(client().get(api("/settings"))).await
}

#[tauri::command]
pub async fn command_set_root(root: Option<String>) -> Result<CommandSettings, String> {
    answer(
        client()
            .put(api("/settings"))
            .json(&serde_json::json!({ "root": root })),
    )
    .await
}

#[tauri::command]
pub async fn command_list_campaigns() -> Result<Vec<String>, String> {
    #[derive(Deserialize)]
    struct Campaigns {
        campaigns: Vec<String>,
    }
    answer::<Campaigns>(client().get(api("/campaigns")))
        .await
        .map(|c| c.campaigns)
}

#[tauri::command]
pub async fn command_create_campaign(name: String) -> Result<String, String> {
    answer::<Named>(
        client()
            .post(api("/campaigns"))
            .json(&serde_json::json!({ "name": name })),
    )
    .await
    .map(|n| n.name)
}

#[tauri::command]
pub async fn command_rename_campaign(name: String, new_name: String) -> Result<Renamed, String> {
    answer(
        client()
            .post(api("/campaigns/rename"))
            .json(&serde_json::json!({ "name": name, "new_name": new_name })),
    )
    .await
}

#[tauri::command]
pub async fn command_get_campaign(name: String) -> Result<CampaignIndex, String> {
    answer(client().get(api_query("/campaign", &[("name", &name)])?)).await
}

#[tauri::command]
pub async fn command_create_track(campaign: String, name: String) -> Result<String, String> {
    answer::<Named>(
        client()
            .post(api("/tracks"))
            .json(&serde_json::json!({ "campaign": campaign, "name": name })),
    )
    .await
    .map(|n| n.name)
}

#[tauri::command]
pub async fn command_rename_track(
    campaign: String,
    name: String,
    new_name: String,
) -> Result<Renamed, String> {
    answer(
        client()
            .post(api("/tracks/rename"))
            .json(&serde_json::json!({
                "campaign": campaign, "name": name, "new_name": new_name,
            })),
    )
    .await
}

#[tauri::command]
pub async fn command_read_note(campaign: String, path: String) -> Result<Note, String> {
    answer(client().get(api_query(
        "/note",
        &[("campaign", &campaign), ("path", &path)],
    )?))
    .await
}

#[tauri::command]
pub async fn command_save_note(
    campaign: String,
    path: String,
    content: String,
    base_hash: String,
) -> Result<SaveOutcome, String> {
    let response = client()
        .put(api("/note"))
        .json(&serde_json::json!({
            "campaign": campaign, "path": path, "content": content, "base_hash": base_hash,
        }))
        .timeout(TIMEOUT)
        .send()
        .await
        .map_err(|e| format!("Failed to connect to the sidecar: {}", e))?;
    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    save_outcome(status, &body)
}

#[tauri::command]
pub async fn command_create_note(
    campaign: String,
    folder: String,
    name: String,
) -> Result<String, String> {
    answer::<AtPath>(client().post(api("/notes")).json(&serde_json::json!({
        "campaign": campaign, "folder": folder, "name": name,
    })))
    .await
    .map(|p| p.path)
}

#[tauri::command]
pub async fn command_rename_note(
    campaign: String,
    path: String,
    new_name: String,
) -> Result<Moved, String> {
    answer(
        client()
            .post(api("/notes/rename"))
            .json(&serde_json::json!({
                "campaign": campaign, "path": path, "new_name": new_name,
            })),
    )
    .await
}

#[tauri::command]
pub async fn command_move_note(
    campaign: String,
    path: String,
    folder: String,
) -> Result<Moved, String> {
    answer(client().post(api("/notes/move")).json(&serde_json::json!({
        "campaign": campaign, "path": path, "folder": folder,
    })))
    .await
}

/// Move a campaign (no `path`), or a note or folder inside one, to the OS
/// trash. The sidecar vouches for the path first, with the same checks as
/// every other Command route; the watcher reports the deletion.
#[tauri::command]
pub async fn command_trash(campaign: String, path: Option<String>) -> Result<(), String> {
    let located: AtPath = answer(
        client()
            .post(api("/locate"))
            .json(&serde_json::json!({ "campaign": campaign, "path": path })),
    )
    .await?;
    trash::delete(&located.path).map_err(|e| format!("Failed to move to trash: {}", e))
}

// ---------------------------------------------------------------------------
// The event relay
// ---------------------------------------------------------------------------

/// Carry the sidecar's change events to every window for the app's
/// lifetime, reconnecting whenever the stream drops. The sidecar opens each
/// stream with a refresh event, so after a gap every window refetches
/// rather than keeping what it had.
pub fn start_event_relay(app: AppHandle) {
    std::thread::spawn(move || {
        let mut delay = RETRY_MIN;
        loop {
            match tauri::async_runtime::block_on(relay(&app)) {
                Ok(()) => delay = RETRY_MIN,
                Err(e) => {
                    eprintln!("Command events: {} (retrying in {:?})", e, delay);
                    delay = (delay * 2).min(RETRY_MAX);
                }
            }
            std::thread::sleep(delay);
        }
    });
}

/// One connection's worth of events. Ok when the stream ends cleanly.
async fn relay(app: &AppHandle) -> Result<(), String> {
    use futures_util::StreamExt;

    let response = client()
        .get(api("/events"))
        .send()
        .await
        .map_err(|e| format!("can't connect to the sidecar: {}", e))?;
    if !response.status().is_success() {
        return Err(format!("the sidecar answered {}", response.status()));
    }
    let mut stream = response.bytes_stream();
    let mut frames = SseFrames::default();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("stream error: {}", e))?;
        for event in frames.push(&chunk) {
            if event["type"] == "vault" {
                let _ = app.emit(VAULT_EVENT, &event);
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn refusal_prefers_the_sidecars_own_message() {
        let msg = refusal(
            StatusCode::CONFLICT,
            r#"{"detail":"A note named 'Ismark' already exists in this campaign"}"#,
        );
        assert_eq!(msg, "A note named 'Ismark' already exists in this campaign");
    }

    #[test]
    fn refusal_without_a_string_detail_reports_status_and_body() {
        // FastAPI's own validation errors carry a list, not a message.
        let msg = refusal(
            StatusCode::UNPROCESSABLE_ENTITY,
            r#"{"detail":[{"loc":["body"]}]}"#,
        );
        assert!(msg.starts_with("Sidecar error (422"), "{msg}");
        let msg = refusal(StatusCode::BAD_GATEWAY, "upstream down");
        assert!(msg.contains("upstream down"), "{msg}");
    }

    #[test]
    fn api_query_encodes_names_the_sidecar_decodes_back() {
        let url = api_query(
            "/note",
            &[
                ("campaign", "Chérie's Tale"),
                ("path", "NPCs/Ismark & co.md"),
            ],
        )
        .unwrap();
        let pairs: Vec<(String, String)> = url.query_pairs().into_owned().collect();
        assert_eq!(
            pairs,
            vec![
                ("campaign".into(), "Chérie's Tale".into()),
                ("path".into(), "NPCs/Ismark & co.md".into()),
            ]
        );
        assert!(url.path().ends_with("/api/command/note"), "{url}");
    }

    #[test]
    fn save_outcome_reads_saved_and_conflict() {
        assert_eq!(
            save_outcome(StatusCode::OK, r#"{"hash":"abc"}"#),
            Ok(SaveOutcome::Saved { hash: "abc".into() })
        );
        assert_eq!(
            save_outcome(
                StatusCode::CONFLICT,
                r#"{"detail":"'NPCs/Ismark.md' changed on disk","hash":"def"}"#
            ),
            Ok(SaveOutcome::Conflict { hash: "def".into() })
        );
    }

    #[test]
    fn save_outcome_without_a_hash_is_an_error_not_a_conflict() {
        let err = save_outcome(
            StatusCode::CONFLICT,
            r#"{"detail":"No campaign folder is set"}"#,
        );
        assert_eq!(err, Err("No campaign folder is set".to_string()));
        let err = save_outcome(StatusCode::NOT_FOUND, r#"{"detail":"Nothing at 'x.md'"}"#);
        assert_eq!(err, Err("Nothing at 'x.md'".to_string()));
    }

    #[test]
    fn save_outcome_serializes_with_a_status_tag() {
        let json = serde_json::to_value(SaveOutcome::Conflict { hash: "h".into() }).unwrap();
        assert_eq!(
            json,
            serde_json::json!({ "status": "conflict", "hash": "h" })
        );
    }
}

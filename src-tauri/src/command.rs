//! Command — Tauri commands over the campaign vault and the live set the
//! sidecar keeps (`sidecar/command/`), the relay that carries their events
//! to every window, and deletion through the OS trash (design doc §6.3).

use reqwest::{RequestBuilder, StatusCode};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

use crate::app_context::{switch_campaign_with, AppContext};
use crate::sidecar_url;
use crate::sse::SseFrames;

/// Change events for the campaign folder, relayed as the sidecar sends them:
/// `{ type: "vault", campaign, paths }`, where a null campaign means
/// "anything may have changed — refetch everything".
pub const VAULT_EVENT: &str = "command://vault";

/// The live set changed: `{ type: "live", campaign, seq, beat, notes }`, a
/// whole snapshot. `seq` grows with every change to that campaign's set.
pub const LIVE_EVENT: &str = "command://live";

/// Generous: a rename rewrites links across every note in the campaign.
const TIMEOUT: Duration = Duration::from_secs(30);
/// Short: quitting waits on it, and a blank folder is all a timeout costs.
const DISCARD_TIMEOUT: Duration = Duration::from_secs(2);
const RETRY_MIN: Duration = Duration::from_secs(1);
const RETRY_MAX: Duration = Duration::from_secs(10);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug)]
pub struct CommandSettings {
    pub(crate) root: Option<String>,
    /// Launching a beat marks it spent (design §4).
    #[serde(default)]
    spend_on_launch: bool,
    /// Folders outside the campaigns the shelf copies from (design §3.6).
    #[serde(default)]
    places: Vec<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct NoteEntry {
    name: String,
    path: String,
    track: Option<String>,
    group: Option<String>,
    /// The date it was spent, as written; None while unspent.
    spent: Option<String>,
    /// Where it came from: a PDF page's file URL (Send to Command).
    #[serde(default)]
    source: Option<String>,
}

/// A link from a beat or a session's plan: the name it gives, and the note
/// it resolves to (None when no single note answers to the name).
#[derive(Serialize, Deserialize, Debug)]
pub struct LinkRef {
    link: String,
    path: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct BeatEntry {
    name: String,
    path: String,
    spent: Option<String>,
    notes: Vec<LinkRef>,
}

/// A line of a session's log: what happened (`launch`, `spent`, `unspent`,
/// `captured`, or `jot` for anything else), when, and the note it names.
#[derive(Serialize, Deserialize, Debug)]
pub struct LogEntry {
    time: Option<String>,
    kind: String,
    link: Option<String>,
    path: Option<String>,
    text: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct SessionEntry {
    name: String,
    path: String,
    date: Option<String>,
    beats: Vec<LinkRef>,
    log: Vec<LogEntry>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct CampaignIndex {
    name: String,
    tracks: Vec<String>,
    notes: Vec<NoteEntry>,
    /// Note names by folder, in the order the GM dragged them.
    note_order: std::collections::BTreeMap<String, Vec<String>>,
    /// Each track's pigment, a hex from Legend Lore's palette.
    pigments: std::collections::BTreeMap<String, String>,
    ambiguous: Vec<String>,
    beats: Vec<BeatEntry>,
    sessions: Vec<SessionEntry>,
}

/// A place's notes, as a campaign's index lists them.
#[derive(Serialize, Deserialize, Debug)]
pub struct PlaceIndex {
    notes: Vec<NoteEntry>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct NewSession {
    path: String,
    name: String,
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

/// What's live in one campaign: the beat it was launched from and the notes
/// in play.
#[derive(Serialize, Deserialize, Debug)]
pub struct LiveSet {
    campaign: String,
    seq: u64,
    beat: Option<String>,
    notes: Vec<String>,
}

/// Where Legend Lore can send a hit: the open campaign's tracks.
#[derive(Serialize, Debug)]
pub struct SendTargets {
    campaign: Option<String>,
    tracks: Vec<String>,
}

/// A hit kept as a note: the campaign it went to and the note's path.
#[derive(Serialize, Debug)]
pub struct Sent {
    campaign: String,
    path: String,
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
pub async fn command_set_spend_on_launch(enabled: bool) -> Result<CommandSettings, String> {
    answer(
        client()
            .put(api("/settings"))
            .json(&serde_json::json!({ "spend_on_launch": enabled })),
    )
    .await
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

/// Ask for the campaigns folder with the native picker and make it the
/// root. `None` when the GM cancels.
///
/// The open campaign lives in the old folder, so it's closed first (and
/// discarded if it's a blank Untitled) while that folder still holds it.
/// The new folder opens on a fresh Untitled, as a first launch does.
#[tauri::command]
pub async fn command_choose_root(app: AppHandle) -> Result<Option<CommandSettings>, String> {
    use tauri_plugin_dialog::DialogExt;

    let picked = app
        .dialog()
        .file()
        .set_title("Choose the folder your campaigns live in")
        .blocking_pick_folder();
    let Some(path) = picked else {
        return Ok(None);
    };
    switch_campaign_with(&app, || async { Ok(None) }).await?;
    let changed = command_set_root(Some(path.to_string())).await;
    open_untitled(&app).await?;
    changed.map(Some)
}

/// Add a folder for the shelf to copy from, picked with the native
/// picker (design §3.6). Its path, as the sidecar keeps it; `None` when
/// the GM cancels.
#[tauri::command]
pub async fn command_add_place(app: AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;

    let picked = app
        .dialog()
        .file()
        .set_title("Choose a folder of notes to copy from")
        .blocking_pick_folder();
    let Some(path) = picked else {
        return Ok(None);
    };
    answer::<AtPath>(
        client()
            .post(api("/places"))
            .json(&serde_json::json!({ "path": path.to_string() })),
    )
    .await
    .map(|p| Some(p.path))
}

#[tauri::command]
pub async fn command_forget_place(path: String) -> Result<CommandSettings, String> {
    answer(
        client()
            .post(api("/places/remove"))
            .json(&serde_json::json!({ "path": path })),
    )
    .await
}

#[tauri::command]
pub async fn command_get_place(path: String) -> Result<PlaceIndex, String> {
    answer(client().get(api_query("/place", &[("path", &path)])?)).await
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

// -- the untitled campaign --------------------------------------------------

/// Open a blank untitled campaign in every window (the sidecar reuses one
/// a crash left behind) and return its name. With no campaigns folder
/// chosen yet, the sidecar sets the default one first.
pub(crate) async fn open_untitled(app: &AppHandle) -> Result<String, String> {
    open_from(app, "/untitled").await
}

/// Launch: open the campaign open when the app last quit, or a blank
/// Untitled if it's gone, as `open_untitled`.
pub(crate) async fn reopen(app: &AppHandle) -> Result<String, String> {
    open_from(app, "/reopen").await
}

async fn open_from(app: &AppHandle, path: &str) -> Result<String, String> {
    let opened = switch_campaign_with(app, || async {
        let named: Named = answer(client().post(api(path))).await?;
        Ok(Some(named.name))
    })
    .await?;
    Ok(opened.unwrap_or_default())
}

/// Have the sidecar remove `campaign` if it's an untitled campaign left
/// blank. Quiet when that fails: the blank folder left behind is the one
/// the next launch reuses.
pub(crate) async fn discard_if_blank(campaign: &str) {
    let _ = client()
        .post(api("/campaigns/discard"))
        .json(&serde_json::json!({ "name": campaign }))
        .timeout(DISCARD_TIMEOUT)
        .send()
        .await;
}

/// New campaign: a fresh Untitled, as on a first launch.
#[tauri::command]
pub async fn command_open_untitled(app: AppHandle) -> Result<String, String> {
    open_untitled(&app).await
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

/// Save the order of the campaign's tracks, by name, as the GM drags their
/// columns. Returns the tracks in their order after.
#[tauri::command]
pub async fn command_order_tracks(
    campaign: String,
    order: Vec<String>,
) -> Result<Vec<String>, String> {
    #[derive(Deserialize)]
    struct Tracks {
        tracks: Vec<String>,
    }
    answer::<Tracks>(
        client()
            .put(api("/tracks/order"))
            .json(&serde_json::json!({ "campaign": campaign, "order": order })),
    )
    .await
    .map(|t| t.tracks)
}

/// Give a track a pigment, or none. Returns every track's pigment after.
#[tauri::command]
pub async fn command_pigment_track(
    campaign: String,
    track: String,
    pigment: Option<String>,
) -> Result<std::collections::BTreeMap<String, String>, String> {
    #[derive(Deserialize)]
    struct Pigments {
        pigments: std::collections::BTreeMap<String, String>,
    }
    answer::<Pigments>(
        client()
            .put(api("/tracks/pigment"))
            .json(&serde_json::json!({ "campaign": campaign, "track": track, "pigment": pigment })),
    )
    .await
    .map(|p| p.pigments)
}

/// Save the order of a folder's notes, by name, as the GM drags them in
/// their column. Returns the order saved.
#[tauri::command]
pub async fn command_order_notes(
    campaign: String,
    folder: String,
    order: Vec<String>,
) -> Result<Vec<String>, String> {
    #[derive(Deserialize)]
    struct Order {
        order: Vec<String>,
    }
    answer::<Order>(
        client()
            .put(api("/notes/order"))
            .json(&serde_json::json!({ "campaign": campaign, "folder": folder, "order": order })),
    )
    .await
    .map(|o| o.order)
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
    order: Option<Vec<String>>,
) -> Result<Moved, String> {
    answer(client().post(api("/notes/move")).json(&serde_json::json!({
        "campaign": campaign, "path": path, "folder": folder, "order": order,
    })))
    .await
}

// -- prep: beats, sessions, spent ------------------------------------------

#[tauri::command]
pub async fn command_create_beat(
    campaign: String,
    name: String,
    notes: Vec<String>,
    session: Option<String>,
) -> Result<String, String> {
    answer::<AtPath>(client().post(api("/beats")).json(&serde_json::json!({
        "campaign": campaign, "name": name, "notes": notes, "session": session,
    })))
    .await
    .map(|p| p.path)
}

/// Save the order of the campaign's beats, by name, as the GM drags those
/// outside a plan. Returns the order saved.
#[tauri::command]
pub async fn command_order_beats(
    campaign: String,
    order: Vec<String>,
) -> Result<Vec<String>, String> {
    #[derive(Deserialize)]
    struct Order {
        order: Vec<String>,
    }
    answer::<Order>(
        client()
            .put(api("/beats/order"))
            .json(&serde_json::json!({ "campaign": campaign, "order": order })),
    )
    .await
    .map(|o| o.order)
}

/// Put a note in a beat or take it out. Returns the beat's notes after.
#[tauri::command]
pub async fn command_set_member(
    campaign: String,
    beat: String,
    note: String,
    member: bool,
) -> Result<Vec<String>, String> {
    #[derive(Deserialize)]
    struct Members {
        notes: Vec<String>,
    }
    answer::<Members>(
        client()
            .post(api("/beats/members"))
            .json(&serde_json::json!({
                "campaign": campaign, "beat": beat, "note": note, "member": member,
            })),
    )
    .await
    .map(|m| m.notes)
}

#[tauri::command]
pub async fn command_create_session(campaign: String) -> Result<NewSession, String> {
    answer(
        client()
            .post(api("/sessions"))
            .json(&serde_json::json!({ "campaign": campaign })),
    )
    .await
}

/// Add, move or remove an entry of a session's plan (`op`). Returns the
/// plan after. A move or removal names the entry it expects at `at`.
// The arguments are the IPC contract with the frontend: each is a named key
// in the `invoke` payload.
#[allow(clippy::too_many_arguments)]
#[tauri::command]
pub async fn command_edit_plan(
    campaign: String,
    session: String,
    op: String,
    beat: Option<String>,
    at: Option<u32>,
    to: Option<u32>,
    expect: Option<String>,
) -> Result<Vec<String>, String> {
    #[derive(Deserialize)]
    struct Plan {
        beats: Vec<String>,
    }
    answer::<Plan>(
        client()
            .post(api("/sessions/plan"))
            .json(&serde_json::json!({
                "campaign": campaign, "session": session, "op": op,
                "beat": beat, "at": at, "to": to, "expect": expect,
            })),
    )
    .await
    .map(|p| p.beats)
}

/// Mark a note spent (today) or unspent. Returns the spent date, if any.
/// Play passes its session, so the change is logged there.
#[tauri::command]
pub async fn command_set_spent(
    campaign: String,
    path: String,
    spent: bool,
    session: Option<String>,
) -> Result<Option<String>, String> {
    #[derive(Deserialize)]
    struct Spent {
        spent: Option<String>,
    }
    answer::<Spent>(client().post(api("/spent")).json(&serde_json::json!({
        "campaign": campaign, "path": path, "spent": spent, "session": session,
    })))
    .await
    .map(|s| s.spent)
}

// -- play: the board, the live set, the log --------------------------------

/// A session's board: JSON Canvas `nodes` and `edges` exactly as on disk,
/// plus `notes`, the note each card shows. Kept as JSON on the way through,
/// so fields Command doesn't know (Obsidian's, a later spec's) reach the
/// frontend untouched.
#[tauri::command]
pub async fn command_get_board(
    campaign: String,
    session: String,
) -> Result<serde_json::Value, String> {
    answer(client().get(api_query(
        "/board",
        &[("campaign", &campaign), ("session", &session)],
    )?))
    .await
}

/// Apply card operations (place, frame, connect, remove) to a session's
/// board. Returns the board after.
#[tauri::command]
pub async fn command_edit_board(
    campaign: String,
    session: String,
    ops: Vec<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    answer(client().post(api("/board")).json(&serde_json::json!({
        "campaign": campaign, "session": session, "ops": ops,
    })))
    .await
}

#[tauri::command]
pub async fn command_get_live(campaign: String) -> Result<LiveSet, String> {
    answer(client().get(api_query("/live", &[("campaign", &campaign)])?)).await
}

/// Launch a beat: its notes become the live set, logged in `session`.
#[tauri::command]
pub async fn command_launch(
    campaign: String,
    beat: String,
    session: Option<String>,
) -> Result<LiveSet, String> {
    answer(client().post(api("/live/launch")).json(&serde_json::json!({
        "campaign": campaign, "beat": beat, "session": session,
    })))
    .await
}

/// Put one note in the live set or take it out.
#[tauri::command]
pub async fn command_set_live(
    campaign: String,
    note: String,
    live: bool,
) -> Result<LiveSet, String> {
    answer(client().post(api("/live/note")).json(&serde_json::json!({
        "campaign": campaign, "note": note, "live": live,
    })))
    .await
}

#[tauri::command]
pub async fn command_stop(campaign: String) -> Result<LiveSet, String> {
    answer(
        client()
            .post(api("/live/stop"))
            .json(&serde_json::json!({ "campaign": campaign })),
    )
    .await
}

/// Add a line to the end of the session note's own text, above its log.
/// Returns the line written.
#[tauri::command]
pub async fn command_jot(
    campaign: String,
    session: String,
    text: String,
) -> Result<String, String> {
    #[derive(Deserialize)]
    struct Line {
        line: String,
    }
    answer::<Line>(client().post(api("/jot")).json(&serde_json::json!({
        "campaign": campaign, "session": session, "text": text,
    })))
    .await
    .map(|l| l.line)
}

// -- cross-tool (design §8) -------------------------------------------------

/// Tell the sidecar which campaign and session are open, so MCP acts on them
/// with no window open (design §6.2). Fire and forget: while the sidecar is
/// down nothing is lost, since the event relay pushes again on reconnecting.
pub fn push_context<T: Serialize>(snapshot: &T) {
    let Ok(body) = serde_json::to_value(snapshot) else {
        return;
    };
    tauri::async_runtime::spawn(async move {
        let _ = client()
            .put(api("/context"))
            .json(&body)
            .timeout(TIMEOUT)
            .send()
            .await;
    });
}

/// The tracks of the campaign open in Command, for Legend Lore's "Send to
/// Command" menu. No campaign open, no tracks.
#[tauri::command]
pub async fn command_send_targets(
    state: tauri::State<'_, AppContext>,
) -> Result<SendTargets, String> {
    #[derive(Deserialize)]
    struct Tracks {
        tracks: Vec<String>,
    }
    let Some(campaign) = state.campaign() else {
        return Ok(SendTargets {
            campaign: None,
            tracks: Vec::new(),
        });
    };
    let found: Tracks =
        answer(client().get(api_query("/tracks", &[("campaign", &campaign)])?)).await?;
    Ok(SendTargets {
        campaign: Some(campaign),
        tracks: found.tracks,
    })
}

/// Keep a Legend Lore hit as a note in the open campaign: in `track`, or
/// on its shelf when there's none. The one crossing between the tools'
/// windows (architecture D4): Legend Lore asks Rust, and Command hears of
/// the new note from the vault watcher.
#[tauri::command]
pub async fn command_send(
    state: tauri::State<'_, AppContext>,
    track: Option<String>,
    name: String,
    text: String,
    source: String,
    cite: String,
) -> Result<Sent, String> {
    let campaign = state
        .campaign()
        .ok_or_else(|| "Open a campaign in Command first".to_string())?;
    let sent: AtPath = answer(client().post(api("/send")).json(&serde_json::json!({
        "campaign": campaign, "track": track, "name": name,
        "text": text, "source": source, "cite": cite,
    })))
    .await?;
    Ok(Sent {
        campaign,
        path: sent.path,
    })
}

/// Copy another campaign's note, or a place's, onto this campaign's
/// shelf. Returns the copy's path.
#[tauri::command]
pub async fn command_copy_note(
    campaign: String,
    from_campaign: Option<String>,
    from_place: Option<String>,
    path: String,
) -> Result<String, String> {
    answer::<AtPath>(client().post(api("/notes/copy")).json(&serde_json::json!({
        "campaign": campaign, "from_campaign": from_campaign,
        "from_place": from_place, "path": path,
    })))
    .await
    .map(|p| p.path)
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
    // A (re)started sidecar knows nothing of what's open: tell it.
    push_context(&app.state::<AppContext>().snapshot());
    let mut stream = response.bytes_stream();
    let mut frames = SseFrames::default();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("stream error: {}", e))?;
        for event in frames.push(&chunk) {
            match event["type"].as_str() {
                Some("vault") => {
                    let _ = app.emit(VAULT_EVENT, &event);
                    // No campaign named: the list itself may have changed.
                    if event["campaign"].is_null() {
                        crate::file_menu::spawn_refresh(app);
                    }
                }
                Some("live") => {
                    let _ = app.emit(LIVE_EVENT, &event);
                }
                _ => {}
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
    fn campaign_index_keeps_prep_fields_on_the_way_through() {
        // Rust re-serialises what the sidecar sends: a field the struct
        // doesn't name would silently vanish before the frontend sees it.
        let sidecar = serde_json::json!({
            "name": "Strahd", "tracks": ["NPCs"], "ambiguous": [],
            "notes": [{"name": "Ismark", "path": "NPCs/Ismark.md", "track": "NPCs", "group": null, "spent": "2026-10-18",
                       "source": "file:///b.pdf#page=3"}],
            "note_order": {"NPCs": ["Ismark", "Ireena"]},
            "pigments": {"NPCs": "#d07c87"},
            "beats": [{"name": "Ambush", "path": "Beats/Ambush.md", "spent": null,
                       "notes": [{"link": "Ismark", "path": "NPCs/Ismark.md"}, {"link": "Wolves", "path": null}]}],
            "sessions": [{"name": "Session 1", "path": "Sessions/Session 1.md", "date": "2026-10-18",
                          "beats": [{"link": "Ambush", "path": "Beats/Ambush.md"}],
                          "log": [{"time": "19:42", "kind": "launch", "link": "Ambush",
                                   "path": "Beats/Ambush.md", "text": "▶ [[Ambush]]"},
                                  {"time": null, "kind": "jot", "link": null, "path": null,
                                   "text": "later"}]}],
        });
        let index: CampaignIndex = serde_json::from_value(sidecar.clone()).unwrap();
        assert_eq!(serde_json::to_value(index).unwrap(), sidecar);
    }

    #[test]
    fn settings_and_live_sets_keep_their_fields_on_the_way_through() {
        let settings = serde_json::json!({
            "root": "/campaigns", "spend_on_launch": true, "places": ["/Homebrew"],
        });
        let parsed: CommandSettings = serde_json::from_value(settings.clone()).unwrap();
        assert_eq!(serde_json::to_value(parsed).unwrap(), settings);

        let live = serde_json::json!({
            "campaign": "Strahd", "seq": 4, "beat": "Beats/Ambush.md",
            "notes": ["NPCs/Ireena.md"],
        });
        let parsed: LiveSet = serde_json::from_value(live.clone()).unwrap();
        assert_eq!(serde_json::to_value(parsed).unwrap(), live);
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

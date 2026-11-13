//! Command — Tauri commands over the campaign vault and the live set the
//! sidecar keeps (`sidecar/command/`), the relay that carries their events
//! to every window, and deletion through the OS trash (design doc §6.3).

use reqwest::{RequestBuilder, StatusCode};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Mutex, PoisonError};
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

/// To every window: show this note in Command, `{ campaign, path }`.
pub const OPEN_NOTE_EVENT: &str = "command://open";

/// To every window: open this encounter in Foresight, `{ campaign, path }`.
pub const OPEN_ENCOUNTER_EVENT: &str = "foresight://open";

/// Generous: a rename rewrites links across every note in the campaign.
const TIMEOUT: Duration = Duration::from_secs(30);
/// Short: quitting waits on it, and a blank folder is all a timeout costs.
const DISCARD_TIMEOUT: Duration = Duration::from_secs(2);
/// Short as well: quitting waits on it, with the sidecar on the same machine.
const HELD_TIMEOUT: Duration = Duration::from_secs(3);
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
    /// "note", or "image" for a picture a track holds (images design §3).
    #[serde(rename = "type")]
    kind: String,
    /// It's in an encounter track: Foresight opens it (Foresight design §3).
    #[serde(default)]
    encounter: bool,
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

#[derive(Serialize, Deserialize, Debug)]
pub struct SessionEntry {
    name: String,
    path: String,
    date: Option<String>,
    beats: Vec<LinkRef>,
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
    /// The notes sharing their name with another of their kind, by path.
    ambiguous: Vec<String>,
    beats: Vec<BeatEntry>,
    sessions: Vec<SessionEntry>,
    /// Every image in the campaign, by path, for notes' embeds (#407).
    #[serde(default)]
    images: Vec<String>,
    /// Each track's kind, "note", "image" or "encounter" (images design
    /// §3.2, Foresight design §3).
    #[serde(default)]
    kinds: std::collections::BTreeMap<String, String>,
    /// The columns each encounter track's next encounter takes (Foresight
    /// design §6).
    #[serde(default)]
    encounter_columns: std::collections::BTreeMap<String, Vec<String>>,
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

/// The open note's text while it isn't on disk: what the editor would save
/// next, with the hash it was loaded at.
#[derive(Deserialize, Clone, Debug, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct HeldNote {
    campaign: String,
    path: String,
    content: String,
    base_hash: String,
}

/// What each window's editor hasn't saved yet (noteBuffer.ts `hold`). The
/// editor saves after a pause in the typing, and a window can close, or the
/// app quit, inside that pause: its webview is gone then, so the text is
/// kept here and saved from here. By window label, with the `seq` of the
/// call that set it, since two calls can land out of order.
#[derive(Default)]
pub struct HeldNotes(Mutex<HashMap<String, (u64, Option<HeldNote>)>>);

impl HeldNotes {
    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<String, (u64, Option<HeldNote>)>> {
        self.0.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Keep `pending` for `window`, or nothing once its text is on disk.
    /// A call older than the one already kept is dropped.
    fn hold(&self, window: &str, seq: u64, pending: Option<HeldNote>) {
        let mut held = self.lock();
        match held.get(window) {
            Some((kept, _)) if *kept > seq => {}
            _ => {
                held.insert(window.to_string(), (seq, pending));
            }
        }
    }

    /// What `window` holds unsaved, and the call that set it.
    fn of(&self, window: &str) -> Option<(u64, HeldNote)> {
        match self.lock().get(window) {
            Some((seq, Some(note))) => Some((*seq, note.clone())),
            _ => None,
        }
    }

    /// Let go of what `window` held at `seq`, unless it has held more since.
    fn release(&self, window: &str, seq: u64) {
        if let Some((kept, note)) = self.lock().get_mut(window) {
            if *kept == seq {
                *note = None;
            }
        }
    }

    /// Everything still held, taken from every window.
    fn take_all(&self) -> Vec<HeldNote> {
        self.lock()
            .values_mut()
            .filter_map(|(_, note)| note.take())
            .collect()
    }
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
    /// Each track's kind: a hit goes to a note track, an image to an image
    /// track (images design §3.2).
    kinds: std::collections::BTreeMap<String, String>,
}

/// One track for Augury's Tracks set: its pigment and its unspent clips by
/// name, which a pad draws one of at random (Augury design §6).
#[derive(Serialize, Debug, PartialEq)]
pub struct DrawTrack {
    name: String,
    pigment: Option<String>,
    notes: Vec<String>,
}

/// What Augury's Tracks set draws from: the open campaign's tracks.
#[derive(Serialize, Debug)]
pub struct DrawTracks {
    campaign: Option<String>,
    tracks: Vec<DrawTrack>,
}

/// One row of an encounter's table (Foresight design §3): its name, the
/// note it links to as the link spells it, whether it's out of the fight,
/// and a cell for each column after the first.
#[derive(Serialize, Deserialize, Debug)]
pub struct EncounterRow {
    name: String,
    #[serde(default)]
    link: Option<String>,
    #[serde(default)]
    out: bool,
    #[serde(default)]
    cells: Vec<String>,
}

/// An encounter as Foresight shows it: the note's table, `round` and
/// `turn`, the hash a save is checked against, and its spent date.
#[derive(Serialize, Deserialize, Debug)]
pub struct Encounter {
    path: String,
    name: String,
    /// The encounter track that holds it.
    track: String,
    hash: String,
    spent: Option<String>,
    round: u32,
    turn: Option<String>,
    columns: Vec<String>,
    rows: Vec<EncounterRow>,
}

/// What Send to Command kept, a hit as a note or an image from the tree:
/// the campaign it went to and its path there.
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
    crate::sidecar_client()
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

/// Not a command: the root changes only through the native picker
/// (`command_choose_root`), never to a path the webview names.
async fn set_root(root: &str) -> Result<CommandSettings, String> {
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
    let changed = set_root(&path.to_string()).await;
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
    allow_campaigns_folder(app).await;
    Ok(opened.unwrap_or_default())
}

/// Let the webview load files from the campaigns folder through the asset
/// protocol, for the images on cards (#407), and nothing outside it. Every
/// campaign opens through `open_from`, after the root is set or changed.
/// A folder stays allowed until the app quits, since Tauri's scope can't
/// take an allow back; each one was the GM's choice.
async fn allow_campaigns_folder(app: &AppHandle) {
    let root = match command_get_settings().await {
        Ok(settings) => settings.root,
        Err(e) => return eprintln!("Command images: no campaigns folder ({})", e),
    };
    if let Some(root) = root {
        if let Err(e) = app.asset_protocol_scope().allow_directory(&root, true) {
            eprintln!("Command images: can't serve {} ({})", root, e);
        }
    }
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
    save_note(&campaign, &path, &content, &base_hash, TIMEOUT).await
}

async fn save_note(
    campaign: &str,
    path: &str,
    content: &str,
    base_hash: &str,
    timeout: Duration,
) -> Result<SaveOutcome, String> {
    let response = client()
        .put(api("/note"))
        .json(&serde_json::json!({
            "campaign": campaign, "path": path, "content": content, "base_hash": base_hash,
        }))
        .timeout(timeout)
        .send()
        .await
        .map_err(|e| format!("Failed to connect to the sidecar: {}", e))?;
    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    save_outcome(status, &body)
}

/// The calling window's unsaved text, or `None` once it has none.
#[tauri::command]
pub fn command_hold_note(
    window: tauri::WebviewWindow,
    held: tauri::State<'_, HeldNotes>,
    seq: u64,
    pending: Option<HeldNote>,
) {
    held.hold(window.label(), seq, pending);
}

/// Save text a window held when it went. The sidecar takes it only over the
/// file the editor loaded (`base_hash`), so a note that changed since, or
/// that the editor's own last save reached first, is left as it is.
async fn save_held(note: &HeldNote) {
    let saved = save_note(
        &note.campaign,
        &note.path,
        &note.content,
        &note.base_hash,
        HELD_TIMEOUT,
    )
    .await;
    match saved {
        Ok(SaveOutcome::Saved { .. }) => {}
        Ok(SaveOutcome::Conflict { .. }) => eprintln!(
            "Command: {} changed on disk, so the text its window held wasn't saved",
            note.path
        ),
        Err(e) => eprintln!(
            "Command: couldn't save the text held for {}: {}",
            note.path, e
        ),
    }
}

/// A window is gone (a pop-out closed or docked): save what its editor
/// hadn't. It stays held until the save returns, so a quit meanwhile still
/// finds it (`save_all_held`).
pub fn on_window_destroyed(app: &AppHandle, label: &str) {
    let Some((seq, note)) = app.state::<HeldNotes>().of(label) else {
        return;
    };
    let app = app.clone();
    let label = label.to_string();
    tauri::async_runtime::spawn(async move {
        save_held(&note).await;
        app.state::<HeldNotes>().release(&label, seq);
    });
}

/// The app is quitting: save what every editor hadn't, before the sidecar
/// stops.
pub(crate) async fn save_all_held(app: &AppHandle) {
    for note in app.state::<HeldNotes>().take_all() {
        save_held(&note).await;
    }
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
#[tauri::command]
pub async fn command_set_spent(
    campaign: String,
    path: String,
    spent: bool,
) -> Result<Option<String>, String> {
    #[derive(Deserialize)]
    struct Spent {
        spent: Option<String>,
    }
    answer::<Spent>(client().post(api("/spent")).json(&serde_json::json!({
        "campaign": campaign, "path": path, "spent": spent,
    })))
    .await
    .map(|s| s.spent)
}

// -- encounters: Foresight's (Foresight design §3) -------------------------

#[tauri::command]
pub async fn command_read_encounter(campaign: String, path: String) -> Result<Encounter, String> {
    answer(client().get(api_query(
        "/encounter",
        &[("campaign", &campaign), ("path", &path)],
    )?))
    .await
}

/// Write an encounter's table, round and turn over its note, if the note is
/// still the version read (`base_hash`); a conflict carries the hash now on
/// disk, as a note's save does.
#[tauri::command]
pub async fn command_save_encounter(
    campaign: String,
    path: String,
    base_hash: String,
    round: u32,
    turn: Option<String>,
    columns: Vec<String>,
    rows: Vec<EncounterRow>,
) -> Result<SaveOutcome, String> {
    let response = client()
        .put(api("/encounter"))
        .json(&serde_json::json!({
            "campaign": campaign, "path": path, "base_hash": base_hash,
            "round": round, "turn": turn, "columns": columns, "rows": rows,
        }))
        .timeout(TIMEOUT)
        .send()
        .await
        .map_err(|e| format!("Failed to connect to the sidecar: {}", e))?;
    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    save_outcome(status, &body)
}

/// A new encounter in `track`, named after it, holding `rows`. With no track
/// named, the campaign's first encounter track, or a new one.
#[tauri::command]
pub async fn command_create_encounter(
    campaign: String,
    track: Option<String>,
    columns: Vec<String>,
    rows: Vec<EncounterRow>,
) -> Result<Encounter, String> {
    answer(client().post(api("/encounter")).json(&serde_json::json!({
        "campaign": campaign, "track": track, "columns": columns, "rows": rows,
    })))
    .await
}

/// The columns `track`'s next encounter takes, kept with the campaign.
#[tauri::command]
pub async fn command_save_encounter_columns(
    campaign: String,
    track: String,
    columns: Vec<String>,
) -> Result<(), String> {
    answer::<serde_json::Value>(
        client()
            .put(api("/tracks/columns"))
            .json(&serde_json::json!({
                "campaign": campaign, "track": track, "columns": columns,
            })),
    )
    .await
    .map(|_| ())
}

/// What one tool asks of the other: a note of a campaign, to show.
#[derive(Serialize, Clone, Debug)]
struct OpenAt {
    campaign: String,
    path: String,
}

/// Bring `tool` forward and hand it the note. A crossing between the tools'
/// windows, so it goes through Rust as Send to Command's does: either tool
/// may be popped out, and drops don't cross windows.
fn open_in(
    app: &AppHandle,
    tool: &str,
    event: &str,
    campaign: String,
    path: String,
) -> Result<(), String> {
    crate::panels::show_panel(app, tool);
    app.emit(event, OpenAt { campaign, path })
        .map_err(|e| e.to_string())
}

/// Foresight's double-click on a linked name: the note, in Command.
#[tauri::command]
pub fn command_open_note(app: AppHandle, campaign: String, path: String) -> Result<(), String> {
    open_in(&app, "command", OPEN_NOTE_EVENT, campaign, path)
}

/// Command's *Open in Foresight* on an encounter note.
#[tauri::command]
pub fn command_open_encounter(
    app: AppHandle,
    campaign: String,
    path: String,
) -> Result<(), String> {
    open_in(&app, "foresight", OPEN_ENCOUNTER_EVENT, campaign, path)
}

// -- play: the board, the live set, jots ------------------------------------

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

/// The operations that lay a session's board out by beat (board toolbar
/// design §6, step 3), unapplied: the frontend applies them through
/// `command_edit_board` as one step it can undo. Returns `{ ops }`.
#[tauri::command]
pub async fn command_arrange_board(
    campaign: String,
    session: String,
) -> Result<serde_json::Value, String> {
    answer(client().get(api_query(
        "/board/arrange",
        &[("campaign", &campaign), ("session", &session)],
    )?))
    .await
}

#[tauri::command]
pub async fn command_get_live(campaign: String) -> Result<LiveSet, String> {
    answer(client().get(api_query("/live", &[("campaign", &campaign)])?)).await
}

/// Launch a beat: its notes become the live set.
#[tauri::command]
pub async fn command_launch(campaign: String, beat: String) -> Result<LiveSet, String> {
    answer(client().post(api("/live/launch")).json(&serde_json::json!({
        "campaign": campaign, "beat": beat,
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

/// Put the live set's notes in this order: the card tray's, dragged.
#[tauri::command]
pub async fn command_order_live(campaign: String, notes: Vec<String>) -> Result<LiveSet, String> {
    answer(client().post(api("/live/order")).json(&serde_json::json!({
        "campaign": campaign, "notes": notes,
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

/// Add a line to the end of the session note's text. Returns the line
/// written.
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
        kinds: std::collections::BTreeMap<String, String>,
    }
    let Some(campaign) = state.campaign() else {
        return Ok(SendTargets {
            campaign: None,
            tracks: Vec::new(),
            kinds: Default::default(),
        });
    };
    let found: Tracks =
        answer(client().get(api_query("/tracks", &[("campaign", &campaign)])?)).await?;
    Ok(SendTargets {
        campaign: Some(campaign),
        tracks: found.tracks,
        kinds: found.kinds,
    })
}

/// A campaign's tracks in display order, each with its unspent clips: a
/// spent note is used up, so a draw never lands on one.
fn draw_tracks(index: CampaignIndex) -> Vec<DrawTrack> {
    index
        .tracks
        .iter()
        .map(|track| DrawTrack {
            name: track.clone(),
            pigment: index.pigments.get(track).cloned(),
            notes: index
                .notes
                .iter()
                .filter(|n| n.track.as_deref() == Some(track.as_str()) && n.spent.is_none())
                .map(|n| n.name.clone())
                .collect(),
        })
        .collect()
}

/// The open campaign's tracks for Augury's Tracks set. A crossing between
/// tools' windows, so it goes through Rust as Send to Command's does: Augury
/// asks, Rust knows the campaign. No campaign open, no tracks.
#[tauri::command]
pub async fn command_draw_tracks(
    state: tauri::State<'_, AppContext>,
) -> Result<DrawTracks, String> {
    let Some(campaign) = state.campaign() else {
        return Ok(DrawTracks {
            campaign: None,
            tracks: Vec::new(),
        });
    };
    let index: CampaignIndex =
        answer(client().get(api_query("/campaign", &[("name", &campaign)])?)).await?;
    Ok(DrawTracks {
        campaign: Some(campaign),
        tracks: draw_tracks(index),
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

#[tauri::command]
pub async fn command_kind_track(
    campaign: String,
    track: String,
    kind: String,
) -> Result<std::collections::BTreeMap<String, String>, String> {
    #[derive(Deserialize)]
    struct Kinds {
        kinds: std::collections::BTreeMap<String, String>,
    }
    answer::<Kinds>(
        client()
            .put(api("/tracks/kind"))
            .json(&serde_json::json!({ "campaign": campaign, "track": track, "kind": kind })),
    )
    .await
    .map(|k| k.kinds)
}

/// Copy an image's bytes into the campaign: into `track`, or onto the
/// shelf. Returns the copy's path, numbered when the name was taken.
async fn post_image(
    campaign: &str,
    name: &str,
    track: Option<&str>,
    bytes: Vec<u8>,
) -> Result<String, String> {
    let mut params = vec![("campaign", campaign), ("name", name)];
    if let Some(track) = track {
        params.push(("track", track));
    }
    let added: AtPath = answer(client().post(api_query("/images", &params)?).body(bytes)).await?;
    Ok(added.path)
}

/// Send an image from Legend Lore's tree to the open campaign (images
/// design §6): copied into `track`, an image track, or onto its shelf when
/// there's none, since the campaign is the unit. Like Send to Command for
/// a hit, the one crossing between the tools' windows (architecture D4).
#[tauri::command]
pub async fn command_send_image(
    state: tauri::State<'_, AppContext>,
    track: Option<String>,
    path: String,
) -> Result<Sent, String> {
    let campaign = state
        .campaign()
        .ok_or_else(|| "Open a campaign in Command first".to_string())?;
    let file = std::path::Path::new(&path);
    let name = file
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .filter(|n| crate::legend_lore::is_image_name(n))
        .ok_or_else(|| format!("{} isn't an image", path))?;
    let bytes = std::fs::read(file).map_err(|e| format!("Can't read {}: {}", name, e))?;
    let path = post_image(&campaign, &name, track.as_deref(), bytes).await?;
    Ok(Sent { campaign, path })
}

/// Add images to an image track (images design §4), picked with the native
/// picker, several at once, and copied in. Their paths; none when the GM
/// cancels.
#[tauri::command]
pub async fn command_pick_images(
    app: AppHandle,
    campaign: String,
    track: String,
) -> Result<Vec<String>, String> {
    use tauri_plugin_dialog::DialogExt;

    let picked = app
        .dialog()
        .file()
        .set_title(format!("Add images to {}", track))
        .add_filter("Images", &["png", "jpg", "jpeg", "gif", "webp", "svg"])
        .blocking_pick_files()
        .unwrap_or_default();
    let mut added = Vec::new();
    for file in picked {
        let path = file.into_path().map_err(|e| e.to_string())?;
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .ok_or_else(|| format!("{} has no file name", path.display()))?;
        let bytes = std::fs::read(&path).map_err(|e| format!("Can't read {}: {}", name, e))?;
        added.push(post_image(&campaign, &name, Some(&track), bytes).await?);
    }
    Ok(added)
}

/// Copy an image dropped from Finder into the campaign: onto the shelf,
/// from a board (#407) or the shelf, or into the image track it was dropped
/// on, named in a `track` header (images design §4). The body is the
/// file's bytes, raw rather than JSON; the names come in headers,
/// URI-encoded since a header is ASCII. Returns the copy's path.
#[tauri::command]
pub async fn command_add_image(request: tauri::ipc::Request<'_>) -> Result<String, String> {
    let tauri::ipc::InvokeBody::Raw(bytes) = request.body() else {
        return Err("The image came without its bytes".to_string());
    };
    let header = |key: &str| {
        request
            .headers()
            .get(key)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| percent_encoding::percent_decode_str(v).decode_utf8().ok())
            .map(|v| v.into_owned())
    };
    let needed =
        |key: &str| header(key).ok_or_else(|| format!("The image came without its {}", key));
    let (campaign, name) = (needed("campaign")?, needed("name")?);
    post_image(&campaign, &name, header("track").as_deref(), bytes.clone()).await
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
                // An agent asking for a session (MCP's set_active_session).
                Some("session") => {
                    if let (Some(campaign), Some(session)) =
                        (event["campaign"].as_str(), event["session"].as_str())
                    {
                        crate::app_context::open_session(app, campaign, session);
                    }
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
                       "source": "file:///b.pdf#page=3", "type": "note", "encounter": true},
                      {"name": "Barovia.png", "path": "Maps/Barovia.png", "track": "Maps", "group": null, "spent": null,
                       "source": null, "type": "image", "encounter": false}],
            "note_order": {"NPCs": ["Ismark", "Ireena"]},
            "pigments": {"NPCs": "#d07c87"},
            "beats": [{"name": "Ambush", "path": "Beats/Ambush.md", "spent": null,
                       "notes": [{"link": "Ismark", "path": "NPCs/Ismark.md"}, {"link": "Wolves", "path": null}]}],
            "sessions": [{"name": "Session 1", "path": "Sessions/Session 1.md", "date": "2026-10-18",
                          "beats": [{"link": "Ambush", "path": "Beats/Ambush.md"}]}],
            "images": ["Maps/Barovia.png"],
            "kinds": {"Maps": "image", "NPCs": "note", "Chase": "encounter"},
            "encounter_columns": {"Chase": ["Name", "Lead"]},
        });
        let index: CampaignIndex = serde_json::from_value(sidecar.clone()).unwrap();
        assert_eq!(serde_json::to_value(index).unwrap(), sidecar);
    }

    #[test]
    fn draw_tracks_keeps_each_tracks_unspent_clips_in_track_order() {
        let index: CampaignIndex = serde_json::from_value(serde_json::json!({
            "name": "Strahd", "tracks": ["NPCs", "Maps", "Secrets"], "ambiguous": [],
            "notes": [
                {"name": "Ismark", "path": "NPCs/Ismark.md", "track": "NPCs", "group": null, "spent": "2026-10-18", "type": "note"},
                {"name": "Ireena", "path": "NPCs/Vallaki/Ireena.md", "track": "NPCs", "group": "Vallaki", "spent": null, "type": "note"},
                {"name": "Barovia.png", "path": "Maps/Barovia.png", "track": "Maps", "group": null, "spent": null, "type": "image"},
                {"name": "Loose", "path": "Loose.md", "track": null, "group": null, "spent": null, "type": "note"},
            ],
            "note_order": {}, "pigments": {"NPCs": "#d07c87"}, "beats": [], "sessions": [],
        }))
        .unwrap();
        let track = |name: &str, pigment: Option<&str>, notes: &[&str]| DrawTrack {
            name: name.into(),
            pigment: pigment.map(Into::into),
            notes: notes.iter().map(|n| n.to_string()).collect(),
        };
        assert_eq!(
            draw_tracks(index),
            vec![
                track("NPCs", Some("#d07c87"), &["Ireena"]),
                track("Maps", None, &["Barovia.png"]),
                track("Secrets", None, &[]),
            ]
        );
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
    fn an_encounter_keeps_its_fields_on_the_way_through() {
        let encounter = serde_json::json!({
            "path": "Encounters/Encounter 4.md", "name": "Encounter 4", "track": "Encounters", "hash": "abc",
            "spent": null, "round": 3, "turn": "Goblin 2", "columns": ["Combatant", "HP"],
            "rows": [
                {"name": "Kira", "link": "Kira", "out": false, "cells": [""]},
                {"name": "Goblin 1", "link": "Goblin", "out": true, "cells": ["0/7"]},
            ],
        });
        let parsed: Encounter = serde_json::from_value(encounter.clone()).unwrap();
        assert_eq!(serde_json::to_value(parsed).unwrap(), encounter);

        // A row sent with its name alone takes no link, in the fight, no cells.
        let row: EncounterRow =
            serde_json::from_value(serde_json::json!({"name": "Kira"})).unwrap();
        assert_eq!(
            serde_json::to_value(row).unwrap(),
            serde_json::json!({"name": "Kira", "link": null, "out": false, "cells": []}),
        );
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

    fn held(content: &str) -> HeldNote {
        HeldNote {
            campaign: "Curse of Strahd".into(),
            path: "NPCs/Ismark.md".into(),
            content: content.into(),
            base_hash: "abc".into(),
        }
    }

    #[test]
    fn a_held_note_reads_what_the_editor_sends() {
        let sent = r#"{"campaign":"Curse of Strahd","path":"NPCs/Ismark.md","content":"Brother.","baseHash":"abc"}"#;
        assert_eq!(
            serde_json::from_str::<HeldNote>(sent).unwrap(),
            held("Brother.")
        );
    }

    #[test]
    fn held_notes_keep_each_windows_latest_text_until_it_is_saved() {
        let notes = HeldNotes::default();
        assert_eq!(notes.of("main"), None);
        notes.hold("main", 1, Some(held("one")));
        notes.hold("main", 2, Some(held("two")));
        notes.hold("panel-command", 7, Some(held("popped out")));
        assert_eq!(notes.of("main"), Some((2, held("two"))));
        // On disk now: the editor says so.
        notes.hold("main", 3, None);
        assert_eq!(notes.of("main"), None);
        assert_eq!(notes.take_all(), vec![held("popped out")]);
        assert_eq!(notes.take_all(), vec![]);
    }

    #[test]
    fn held_notes_drop_a_call_that_lands_after_a_later_one() {
        let notes = HeldNotes::default();
        notes.hold("main", 5, Some(held("later")));
        notes.hold("main", 4, Some(held("earlier")));
        assert_eq!(notes.of("main"), Some((5, held("later"))));
        notes.hold("main", 6, None);
        notes.hold("main", 5, Some(held("later")));
        assert_eq!(notes.of("main"), None);
    }

    #[test]
    fn a_saved_held_note_is_released_unless_the_window_held_more_since() {
        let notes = HeldNotes::default();
        notes.hold("panel-command", 1, Some(held("one")));
        notes.release("panel-command", 1);
        assert_eq!(notes.of("panel-command"), None);

        notes.hold("panel-command", 2, Some(held("two")));
        notes.hold("panel-command", 3, Some(held("three")));
        notes.release("panel-command", 2);
        assert_eq!(notes.of("panel-command"), Some((3, held("three"))));
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

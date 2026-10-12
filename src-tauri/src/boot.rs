//! Cold start behind the splash window.
//!
//! The splash opens first and the tool windows stay hidden until every step
//! here has settled. Steps report into `BootState`; the splash pulls it with
//! `get_boot_state` when it mounts and follows `boot://update` after that.
//! No step blocks the boot: a failure holds the splash on its warning for a
//! moment, then the tools open anyway and the status bar's lamps carry the
//! state from there.

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::Ordering;
use std::sync::{mpsc, Mutex, PoisonError};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

use crate::{ModelsStatus, SidecarFailedPayload};

pub const SPLASH_LABEL: &str = "splash";

/// Step ids in lamp order. The splash owns the copy and the grouping by tool.
const STEPS: [&str; 7] = [
    "settings", "sidecar", "store", "embedder", "reranker", "spelling", "library",
];

/// The steps the sidecar warms on its own thread and reports at `/api/boot`.
const WARMUP: [&str; 2] = ["reranker", "spelling"];

/// How long the splash waits on the embedder probe and the warm-up before the
/// tools open without them. A search then pays whatever is left.
const WARMUP_DEADLINE: Duration = Duration::from_secs(15);
/// A stat on an unmounted network share can hang for far longer than this.
const LIBRARY_DEADLINE: Duration = Duration::from_secs(5);
const POLL_INTERVAL: Duration = Duration::from_millis(150);

/// How long the splash stays up once everything has settled: a beat on
/// "Ready", longer when there is a warning to read.
const HOLD_READY: Duration = Duration::from_millis(400);
const HOLD_WARNING: Duration = Duration::from_millis(1500);

const SIDECAR_DOWN: &str = "Skipped: the sidecar is down";

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum StepState {
    Pending,
    Running,
    Done,
    Failed,
    Skipped,
}

impl StepState {
    fn settled(self) -> bool {
        matches!(self, Self::Done | Self::Failed | Self::Skipped)
    }
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct BootStep {
    id: &'static str,
    state: StepState,
    /// The sentence the splash shows for a failed or skipped step.
    detail: Option<String>,
}

#[derive(Serialize, Clone, Debug)]
pub struct BootSnapshot {
    /// Bumped on every change, so the splash can drop a pulled snapshot that
    /// lands after a newer pushed one.
    seq: u64,
    steps: Vec<BootStep>,
    finished: bool,
}

pub struct BootState(Mutex<BootSnapshot>);

impl BootState {
    pub fn new() -> Self {
        Self(Mutex::new(BootSnapshot {
            seq: 0,
            steps: STEPS
                .iter()
                .map(|&id| BootStep {
                    id,
                    state: StepState::Pending,
                    detail: None,
                })
                .collect(),
            finished: false,
        }))
    }

    fn snapshot(&self) -> BootSnapshot {
        self.0
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    fn state_of(&self, id: &str) -> StepState {
        self.snapshot()
            .steps
            .iter()
            .find(|s| s.id == id)
            .map_or(StepState::Pending, |s| s.state)
    }

    /// Record a step's state. `None` when nothing changed, so there is
    /// nothing to emit.
    fn set(&self, id: &str, state: StepState, detail: Option<String>) -> Option<BootSnapshot> {
        let mut snap = self.0.lock().unwrap_or_else(PoisonError::into_inner);
        let step = snap.steps.iter_mut().find(|s| s.id == id)?;
        if step.state == state && step.detail == detail {
            return None;
        }
        step.state = state;
        step.detail = detail;
        snap.seq += 1;
        Some(snap.clone())
    }

    fn finish(&self) -> BootSnapshot {
        let mut snap = self.0.lock().unwrap_or_else(PoisonError::into_inner);
        snap.finished = true;
        snap.seq += 1;
        snap.clone()
    }
}

#[tauri::command]
pub fn get_boot_state(state: tauri::State<BootState>) -> BootSnapshot {
    state.snapshot()
}

/// Run the cold start on its own thread, so setup() returns at once and the
/// splash can paint while the sidecar comes up.
pub fn start(app: AppHandle, spawned: Result<(), String>, app_data_dir: PathBuf) {
    std::thread::spawn(move || run(&app, spawned, &app_data_dir));
}

fn run(app: &AppHandle, spawned: Result<(), String>, app_data_dir: &Path) {
    let boot = app.state::<BootState>();
    let set = |id: &str, state: StepState, detail: Option<String>| {
        if let Some(snap) = boot.set(id, state, detail) {
            let _ = app.emit("boot://update", &snap);
        }
    };

    set("settings", StepState::Running, None);
    let folder = match read_library_folder(&app_data_dir.join("settings.json")) {
        Ok(folder) => {
            set("settings", StepState::Done, None);
            folder
        }
        Err(detail) => {
            set("settings", StepState::Failed, Some(detail));
            None
        }
    };

    // On its own thread, alongside everything else: see LIBRARY_DEADLINE.
    set("library", StepState::Running, None);
    let library_started = Instant::now();
    let (library_tx, library_rx) = mpsc::channel();
    let checked = folder.clone();
    std::thread::spawn(move || {
        let _ = library_tx.send(check_library(checked.as_deref()));
    });

    let up = settle_sidecar(app, spawned, app_data_dir, &set);
    if up {
        crate::command::start_event_relay(app.clone());
        // Command opens on a blank Untitled, as Live opens on an empty set,
        // before any window asks what's open.
        if let Err(e) = tauri::async_runtime::block_on(crate::command::open_untitled(app)) {
            eprintln!("Command couldn't open an untitled campaign: {}", e);
        }
    }

    // The tool window loads behind the splash from here on. Its first calls
    // need the sidecar settled, whichever way it went.
    crate::open_tool_window(app);

    if up {
        set("embedder", StepState::Running, None);
        let (embedder_tx, embedder_rx) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = embedder_tx.send(embedder_outcome(
                fetch::<ModelsStatus>("/api/models/status").as_ref(),
            ));
        });
        follow_warmup(&boot, &set, embedder_rx);
    } else {
        for id in ["store", "embedder", "reranker", "spelling"] {
            if !boot.state_of(id).settled() {
                set(id, StepState::Skipped, Some(SIDECAR_DOWN.into()));
            }
        }
    }

    let remaining = LIBRARY_DEADLINE.saturating_sub(library_started.elapsed());
    let (state, detail) = library_rx.recv_timeout(remaining).unwrap_or_else(|_| {
        let folder = folder.as_deref().unwrap_or(Path::new(""));
        (
            StepState::Failed,
            Some(format!(
                "Library folder isn't responding: {}",
                folder.display()
            )),
        )
    });
    set("library", state, detail);

    let snap = boot.finish();
    let _ = app.emit("boot://update", &snap);
    std::thread::sleep(hold(&snap));

    crate::show_tool_window(app);
    if let Some(splash) = app.get_webview_window(SPLASH_LABEL) {
        // destroy, not close: close() would reach the hide-to-tray handler.
        let _ = splash.destroy();
    }
}

/// Settle the sidecar and store lamps. True when the sidecar is serving.
///
/// Two milestones, two lamps: the port file lands once Python is up, and the
/// socket accepts once the store is open and the app is serving.
fn settle_sidecar(
    app: &AppHandle,
    spawned: Result<(), String>,
    app_data_dir: &Path,
    set: &impl Fn(&str, StepState, Option<String>),
) -> bool {
    let log_path = app_data_dir.join("sidecar.log");
    let record_failure = |message: String| {
        crate::record_sidecar_failure(
            app,
            SidecarFailedPayload {
                log_path: log_path.to_string_lossy().into_owned(),
                message,
            },
        );
    };

    if let Err(message) = spawned {
        set(
            "sidecar",
            StepState::Failed,
            Some("Sidecar didn't start. Search and indexing are offline".into()),
        );
        record_failure(message);
        return false;
    }

    set("sidecar", StepState::Running, None);
    let mut port_seen = false;
    let port_file = app_data_dir.join("chroma_db").join("sidecar.port");
    let result = crate::wait_for_sidecar(&port_file, &log_path, || {
        port_seen = true;
        set("sidecar", StepState::Done, None);
        set("store", StepState::Running, None);
    });
    match result {
        Ok(port) => {
            crate::SIDECAR_PORT.store(port, Ordering::Relaxed);
            set("store", StepState::Done, None);
            true
        }
        Err(message) => {
            eprintln!("{}", message);
            if port_seen {
                set(
                    "store",
                    StepState::Failed,
                    Some("Library store didn't open. Search and indexing are offline".into()),
                );
            } else {
                set(
                    "sidecar",
                    StepState::Failed,
                    Some("Sidecar didn't start. Search and indexing are offline".into()),
                );
            }
            record_failure(message);
            false
        }
    }
}

#[derive(Deserialize)]
struct Warmup {
    steps: HashMap<String, String>,
}

/// Poll the sidecar's warm-up and collect the embedder probe until both
/// have settled or the deadline passes.
fn follow_warmup(
    boot: &BootState,
    set: &impl Fn(&str, StepState, Option<String>),
    embedder_rx: mpsc::Receiver<(StepState, Option<String>)>,
) {
    let deadline = Instant::now() + WARMUP_DEADLINE;
    let mut embedder_pending = true;
    loop {
        if embedder_pending {
            if let Ok((state, detail)) = embedder_rx.try_recv() {
                set("embedder", state, detail);
                embedder_pending = false;
            }
        }
        if let Some(warmup) = fetch::<Warmup>("/api/boot") {
            for id in WARMUP {
                let state = warmup_state(warmup.steps.get(id).map(String::as_str));
                set(id, state, warmup_detail(id, state));
            }
        }
        let warm = WARMUP.iter().all(|id| boot.state_of(id).settled());
        if warm && !embedder_pending {
            return;
        }
        if Instant::now() >= deadline {
            if embedder_pending {
                set(
                    "embedder",
                    StepState::Failed,
                    Some("Embedder didn't answer. Search waits for it".into()),
                );
            }
            for id in WARMUP {
                if !boot.state_of(id).settled() {
                    set(
                        id,
                        StepState::Skipped,
                        Some("Still loading. The first search may be slow".into()),
                    );
                }
            }
            return;
        }
        std::thread::sleep(POLL_INTERVAL);
    }
}

fn fetch<T: DeserializeOwned>(path: &str) -> Option<T> {
    let url = format!("{}{}", crate::sidecar_url(), path);
    tauri::async_runtime::block_on(async move {
        let resp = reqwest::Client::new()
            .get(url)
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .ok()?;
        if !resp.status().is_success() {
            return None;
        }
        resp.json::<T>().await.ok()
    })
}

/// The Legend Lore library folder named in the settings store. No file yet
/// is a first launch, not a failure.
fn read_library_folder(settings: &Path) -> Result<Option<PathBuf>, String> {
    let unreadable = || "Settings file is unreadable, so defaults apply".to_string();
    let raw = match std::fs::read_to_string(settings) {
        Ok(raw) => raw,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(unreadable()),
    };
    let json: serde_json::Value = serde_json::from_str(&raw).map_err(|_| unreadable())?;
    Ok(json
        .get("selectedFolder")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(PathBuf::from))
}

fn check_library(folder: Option<&Path>) -> (StepState, Option<String>) {
    let Some(folder) = folder else {
        return (
            StepState::Skipped,
            Some("No library folder chosen yet".into()),
        );
    };
    match std::fs::read_dir(folder) {
        Ok(_) => (StepState::Done, None),
        Err(_) => (
            StepState::Failed,
            Some(format!(
                "Library folder isn't reachable: {}",
                folder.display()
            )),
        ),
    }
}

/// Same two states the status bar's embedder lamp tells apart: the runtime
/// isn't answering, or it answers without the model.
fn embedder_outcome(models: Option<&ModelsStatus>) -> (StepState, Option<String>) {
    match models.and_then(|m| m.models.iter().find(|m| m.role == "embed")) {
        Some(m) if m.ready => (StepState::Done, None),
        Some(m) if m.runtime_up => (
            StepState::Failed,
            Some(format!(
                "Embedder is running without {}. Search waits for it",
                m.model
            )),
        ),
        _ => (
            StepState::Failed,
            Some("Embedder isn't running. Search waits for it".into()),
        ),
    }
}

fn warmup_state(raw: Option<&str>) -> StepState {
    match raw {
        Some("running") => StepState::Running,
        Some("done") => StepState::Done,
        Some("failed") => StepState::Failed,
        Some("skipped") => StepState::Skipped,
        _ => StepState::Pending,
    }
}

fn warmup_detail(id: &str, state: StepState) -> Option<String> {
    let text = match (id, state) {
        ("reranker", StepState::Failed) => "Reranker didn't load. The first search tries again",
        ("reranker", StepState::Skipped) => "Reranker is turned off",
        ("spelling", StepState::Failed) => {
            "Spelling vocabulary didn't build. The first search tries again"
        }
        _ => return None,
    };
    Some(text.into())
}

fn hold(snap: &BootSnapshot) -> Duration {
    if snap.steps.iter().any(|s| s.state == StepState::Failed) {
        HOLD_WARNING
    } else {
        HOLD_READY
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ModelStatus;

    fn embed_row(runtime_up: bool, ready: bool) -> ModelsStatus {
        ModelsStatus {
            models: vec![ModelStatus {
                role: "embed".into(),
                runtime: "ollama".into(),
                model: "bge-m3".into(),
                runtime_up,
                ready,
            }],
        }
    }

    #[test]
    fn set_reports_only_changes_and_bumps_seq() {
        let boot = BootState::new();
        let first = boot.set("sidecar", StepState::Running, None).unwrap();
        assert_eq!(first.seq, 1);
        assert!(boot.set("sidecar", StepState::Running, None).is_none());
        let second = boot.set("sidecar", StepState::Done, None).unwrap();
        assert_eq!(second.seq, 2);
        assert_eq!(boot.state_of("sidecar"), StepState::Done);
    }

    #[test]
    fn set_ignores_an_unknown_step() {
        let boot = BootState::new();
        assert!(boot.set("nope", StepState::Done, None).is_none());
        assert_eq!(boot.snapshot().seq, 0);
    }

    #[test]
    fn a_warning_holds_the_splash_longer() {
        let boot = BootState::new();
        assert_eq!(hold(&boot.finish()), HOLD_READY);
        boot.set("embedder", StepState::Failed, Some("x".into()));
        assert_eq!(hold(&boot.finish()), HOLD_WARNING);
    }

    #[test]
    fn a_skipped_step_is_not_a_warning() {
        let boot = BootState::new();
        boot.set("library", StepState::Skipped, Some("x".into()));
        assert_eq!(hold(&boot.finish()), HOLD_READY);
    }

    #[test]
    fn embedder_outcome_tells_down_from_missing_model() {
        assert_eq!(
            embedder_outcome(Some(&embed_row(true, true))).0,
            StepState::Done
        );

        let (state, detail) = embedder_outcome(Some(&embed_row(true, false)));
        assert_eq!(state, StepState::Failed);
        assert!(detail.unwrap().contains("bge-m3"));

        let (state, detail) = embedder_outcome(Some(&embed_row(false, false)));
        assert_eq!(state, StepState::Failed);
        assert!(detail.unwrap().contains("isn't running"));

        // No answer from the sidecar at all reads the same as a down runtime.
        assert_eq!(embedder_outcome(None).0, StepState::Failed);
    }

    #[test]
    fn warmup_state_maps_the_sidecar_strings() {
        assert_eq!(warmup_state(Some("running")), StepState::Running);
        assert_eq!(warmup_state(Some("done")), StepState::Done);
        assert_eq!(warmup_state(Some("failed")), StepState::Failed);
        assert_eq!(warmup_state(Some("skipped")), StepState::Skipped);
        assert_eq!(warmup_state(Some("pending")), StepState::Pending);
        assert_eq!(warmup_state(None), StepState::Pending);
    }

    fn scratch_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "unseen-servant-boot-{}-{}",
            name,
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn read_library_folder_handles_first_launch_and_damage() {
        let dir = scratch_dir("settings");
        let settings = dir.join("settings.json");

        assert_eq!(read_library_folder(&settings), Ok(None));

        std::fs::write(&settings, r#"{"selectedFolder": "/Volumes/Tomes"}"#).unwrap();
        assert_eq!(
            read_library_folder(&settings),
            Ok(Some(PathBuf::from("/Volumes/Tomes")))
        );

        std::fs::write(&settings, r#"{"selectedFolder": ""}"#).unwrap();
        assert_eq!(read_library_folder(&settings), Ok(None));

        std::fs::write(&settings, "{not json").unwrap();
        assert!(read_library_folder(&settings).is_err());

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn check_library_reads_the_folder() {
        let dir = scratch_dir("library");
        assert_eq!(check_library(Some(&dir)).0, StepState::Done);
        assert_eq!(check_library(Some(&dir.join("gone"))).0, StepState::Failed);
        assert_eq!(check_library(None).0, StepState::Skipped);
        let _ = std::fs::remove_dir_all(&dir);
    }
}

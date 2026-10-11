//! Server-sent events from the sidecar: Legend Lore's sync progress and
//! Command's change events both arrive as `data:` frames of JSON.

/// Splits an SSE byte stream into its `data:` frames' JSON. Buffers bytes,
/// not text, so a multibyte character split across chunks survives; frames
/// that aren't JSON data (comments, keep-alives) are skipped.
#[derive(Default)]
pub(crate) struct SseFrames {
    buffer: Vec<u8>,
}

impl SseFrames {
    pub(crate) fn push(&mut self, chunk: &[u8]) -> Vec<serde_json::Value> {
        self.buffer.extend_from_slice(chunk);
        let mut out = Vec::new();
        while let Some(pos) = self.buffer.windows(2).position(|w| w == b"\n\n") {
            let frame: Vec<u8> = self.buffer.drain(..pos + 2).collect();
            if let Some(data) = frame[..pos].strip_prefix(b"data: ") {
                if let Ok(json) = serde_json::from_slice(data) {
                    out.push(json);
                }
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sse_frames_reassembles_frames_split_across_chunks() {
        let mut frames = SseFrames::default();
        assert!(frames.push(b"data: {\"event\":\"prog").is_empty());
        let out = frames.push(b"ress\"}\n\ndata: {\"event\":\"started\"}\n\n");
        assert_eq!(out.len(), 2);
        assert_eq!(out[0]["event"], "progress");
        assert_eq!(out[1]["event"], "started");
    }

    #[test]
    fn sse_frames_keeps_a_multibyte_char_split_across_chunks() {
        let bytes = "data: {\"current_file\":\"Grimoire é.pdf\"}\n\n".as_bytes();
        let cut = bytes.iter().position(|&b| b == 0xC3).unwrap() + 1;
        let mut frames = SseFrames::default();
        assert!(frames.push(&bytes[..cut]).is_empty());
        let out = frames.push(&bytes[cut..]);
        assert_eq!(out[0]["current_file"], "Grimoire é.pdf");
    }

    #[test]
    fn sse_frames_skips_frames_that_are_not_json_data() {
        let mut frames = SseFrames::default();
        let out =
            frames.push(b": keep-alive\n\ndata: not json\n\ndata: {\"event\":\"started\"}\n\n");
        assert_eq!(out.len(), 1);
        assert_eq!(out[0]["event"], "started");
    }
}

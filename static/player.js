/**
 * player.js -- Handles the result page: summary display and MIDI playback.
 *
 * Reads the job_id from the URL, fetches job metadata from /api/jobs/{id},
 * loads the MIDI file with @tonejs/midi, and plays it back using Tone.js.
 */

(function () {
    "use strict";

    // --- DOM elements ---
    const loadingText = document.getElementById("loading-text");
    const summarySection = document.getElementById("summary-section");
    const playerSection = document.getElementById("player-section");
    const downloadsSection = document.getElementById("downloads-section");
    const errorBox = document.getElementById("error-box");
    const errorMessage = document.getElementById("error-message");

    const numNotes = document.getElementById("num-notes");
    const duration = document.getElementById("duration");
    const pitchRange = document.getElementById("pitch-range");
    const timeSpan = document.getElementById("time-span");

    const playBtn = document.getElementById("play-btn");
    const pauseBtn = document.getElementById("pause-btn");
    const stopBtn = document.getElementById("stop-btn");
    const playbackTime = document.getElementById("playback-time");
    const playbackProgress = document.getElementById("playback-progress");

    const midiDownload = document.getElementById("midi-download");
    const abcDownload = document.getElementById("abc-download");
    const sheetSection = document.getElementById("sheet-section");

    // --- State ---
    let synth = null;
    let midiData = null;
    let scheduledEvents = [];
    let totalDuration = 0;
    let progressInterval = null;

    // --- Helpers ---
    function formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, "0")}`;
    }

    function showError(message) {
        loadingText.hidden = true;
        errorMessage.textContent = message;
        errorBox.hidden = false;
    }

    // --- ABC synth player (note-highlighting visual widget) ---
    function CursorControl() {
        this.onStart = function () {
            var svg = document.querySelector("#sheet-music svg");
            if (!svg) return;
            var cursor = document.createElementNS("http://www.w3.org/2000/svg", "line");
            cursor.setAttribute("class", "abcjs-cursor");
            cursor.setAttributeNS(null, "x1", 0);
            cursor.setAttributeNS(null, "y1", 0);
            cursor.setAttributeNS(null, "x2", 0);
            cursor.setAttributeNS(null, "y2", 0);
            svg.appendChild(cursor);
        };

        this.onEvent = function (ev) {
            // Remove previous highlights
            var lastSelection = document.querySelectorAll("#sheet-music svg .abcjs-highlight");
            for (var k = 0; k < lastSelection.length; k++) {
                lastSelection[k].classList.remove("abcjs-highlight");
            }

            // Highlight current notes
            for (var i = 0; i < ev.elements.length; i++) {
                var note = ev.elements[i];
                for (var j = 0; j < note.length; j++) {
                    note[j].classList.add("abcjs-highlight");
                }
            }

            // Move cursor line
            var cursor = document.querySelector("#sheet-music svg .abcjs-cursor");
            if (cursor) {
                cursor.setAttribute("x1", ev.left - 2);
                cursor.setAttribute("x2", ev.left - 2);
                cursor.setAttribute("y1", ev.top);
                cursor.setAttribute("y2", ev.top + ev.height);
            }
        };

        this.onFinished = function () {
            var els = document.querySelectorAll("#sheet-music svg .abcjs-highlight");
            for (var i = 0; i < els.length; i++) {
                els[i].classList.remove("abcjs-highlight");
            }
            var cursor = document.querySelector("#sheet-music svg .abcjs-cursor");
            if (cursor) {
                cursor.setAttribute("x1", 0);
                cursor.setAttribute("x2", 0);
                cursor.setAttribute("y1", 0);
                cursor.setAttribute("y2", 0);
            }
        };
    }

    function initAbcPlayer(visualObj) {
        var abcSynthControl = new ABCJS.synth.SynthController();
        abcSynthControl.load("#abc-player", new CursorControl(), {
            displayPlay: true,
            displayProgress: true,
            displayRestart: true,
        });

        var midiBuffer = new ABCJS.synth.CreateSynth();
        midiBuffer.init({ visualObj: visualObj }).then(function () {
            abcSynthControl.setTune(visualObj, false).then(function () {
                console.log("ABC audio player loaded.");
            }).catch(function (error) {
                console.warn("ABC audio problem:", error);
            });
        }).catch(function (error) {
            console.warn("ABC synth init problem:", error);
        });
    }

    // --- Load job data ---
    async function init() {
        const params = new URLSearchParams(window.location.search);
        const jobId = params.get("job");

        if (!jobId) {
            showError("No job ID provided. Please go back and transcribe a file.");
            return;
        }

        try {
            // Fetch job metadata
            const metaResp = await fetch(`/api/jobs/${jobId}`);
            if (!metaResp.ok) {
                const err = await metaResp.json();
                throw new Error(err.detail || "Job not found.");
            }
            const meta = await metaResp.json();

            // Populate summary
            const s = meta.summary;
            numNotes.textContent = s.num_notes;
            duration.textContent = `${s.duration_seconds}s`;
            pitchRange.textContent = s.pitch_range.length
                ? `${s.pitch_range[0]} - ${s.pitch_range[1]}`
                : "N/A";
            timeSpan.textContent = s.time_span.length
                ? `${s.time_span[0]}s - ${s.time_span[1]}s`
                : "N/A";

            // Download links
            midiDownload.href = meta.midi_url;
            midiDownload.download = `${jobId}.mid`;

            if (meta.abc_url) {
                abcDownload.href = meta.abc_url;
                abcDownload.download = `${jobId}.abc`;
                abcDownload.hidden = false;

                // Fetch ABC text, render sheet music, and set up synth player
                try {
                    const abcResp = await fetch(meta.abc_url);
                    if (abcResp.ok) {
                        const abcText = await abcResp.text();
                        const visualObj = ABCJS.renderAbc("sheet-music", abcText, {
                            responsive: "resize",
                            staffwidth: 800,
                            add_classes: true,
                        })[0];

                        // Initialize the abcjs synth player widget
                        if (ABCJS.synth.supportsAudio()) {
                            initAbcPlayer(visualObj);
                        }

                        sheetSection.hidden = false;
                    }
                } catch (e) {
                    // Sheet music rendering is best-effort; don't block the page
                    console.warn("Failed to render sheet music:", e);
                }
            }

            // Load MIDI for playback
            const midiResp = await fetch(meta.midi_url);
            const midiArrayBuffer = await midiResp.arrayBuffer();
            midiData = new Midi(midiArrayBuffer);
            totalDuration = midiData.duration;

            // Show all sections
            loadingText.hidden = true;
            summarySection.hidden = false;
            playerSection.hidden = false;
            downloadsSection.hidden = false;

        } catch (err) {
            showError(`Failed to load results: ${err.message}`);
        }
    }

    // --- Playback controls ---
    function startProgressTracker() {
        stopProgressTracker();
        progressInterval = setInterval(() => {
            const elapsed = Tone.Transport.seconds;
            playbackTime.textContent = formatTime(elapsed);
            if (totalDuration > 0) {
                playbackProgress.value = Math.min(
                    (elapsed / totalDuration) * 100,
                    100
                );
            }
            // Auto-stop at the end
            if (elapsed >= totalDuration) {
                stopPlayback();
            }
        }, 100);
    }

    function stopProgressTracker() {
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }
    }

    function scheduleMidi() {
        if (!midiData || !synth) return;

        // Clear any previously scheduled events
        scheduledEvents.forEach((id) => Tone.Transport.clear(id));
        scheduledEvents = [];

        midiData.tracks.forEach((track) => {
            track.notes.forEach((note) => {
                const eventId = Tone.Transport.schedule((time) => {
                    synth.triggerAttackRelease(
                        note.name,
                        note.duration,
                        time,
                        note.velocity
                    );
                }, note.time);
                scheduledEvents.push(eventId);
            });
        });
    }

    async function startPlayback() {
        await Tone.start();

        if (!synth) {
            synth = new Tone.PolySynth(Tone.Synth, {
                maxPolyphony: 64,
                voice: Tone.Synth,
                options: {
                    envelope: {
                        attack: 0.02,
                        decay: 0.3,
                        sustain: 0.2,
                        release: 0.8,
                    },
                },
            }).toDestination();
        }

        scheduleMidi();

        Tone.Transport.start();
        startProgressTracker();

        playBtn.disabled = true;
        pauseBtn.disabled = false;
        stopBtn.disabled = false;
    }

    function pausePlayback() {
        Tone.Transport.pause();
        stopProgressTracker();

        playBtn.disabled = false;
        playBtn.textContent = "Resume";
        pauseBtn.disabled = true;
    }

    function stopPlayback() {
        Tone.Transport.stop();
        Tone.Transport.position = 0;
        stopProgressTracker();

        // Clear scheduled events
        scheduledEvents.forEach((id) => Tone.Transport.clear(id));
        scheduledEvents = [];

        playbackTime.textContent = "0:00";
        playbackProgress.value = 0;

        playBtn.disabled = false;
        playBtn.textContent = "Play";
        pauseBtn.disabled = true;
        stopBtn.disabled = true;
    }

    // --- Event listeners ---
    playBtn.addEventListener("click", startPlayback);
    pauseBtn.addEventListener("click", pausePlayback);
    stopBtn.addEventListener("click", stopPlayback);

    // --- Initialize ---
    init();
})();

/**
 * upload.js -- Handles the upload form on index.html.
 *
 * Responsibilities:
 *  - Drag-and-drop and click-to-browse file selection
 *  - Slider value display
 *  - Form submission via fetch() to POST /api/transcribe
 *  - Show/hide processing spinner
 *  - Redirect to result.html on success
 */

(function () {
    "use strict";

    // --- DOM elements ---
    const form = document.getElementById("upload-form");
    const fileInput = document.getElementById("file-input");
    const dropZone = document.getElementById("drop-zone");
    const fileNameDisplay = document.getElementById("file-name");
    const submitBtn = document.getElementById("submit-btn");
    const dialog = document.getElementById("processing-dialog");
    const errorBox = document.getElementById("error-box");
    const errorMessage = document.getElementById("error-message");

    // Sliders
    const onsetSlider = document.getElementById("onset-threshold");
    const frameSlider = document.getElementById("frame-threshold");
    const noteLenSlider = document.getElementById("min-note-length");
    const onsetValue = document.getElementById("onset-value");
    const frameValue = document.getElementById("frame-value");
    const noteLenValue = document.getElementById("note-len-value");

    // --- Slider live updates ---
    onsetSlider.addEventListener("input", () => {
        onsetValue.textContent = onsetSlider.value;
    });
    frameSlider.addEventListener("input", () => {
        frameValue.textContent = frameSlider.value;
    });
    noteLenSlider.addEventListener("input", () => {
        noteLenValue.textContent = noteLenSlider.value;
    });

    // --- File selection ---
    let selectedFile = null;
    const dropZoneText = dropZone.querySelector("p");

    function onFileSelected(file) {
        selectedFile = file;
        // Replace drop zone text with filename and disable further interaction
        dropZoneText.textContent = file.name;
        dropZone.classList.add("has-file");
        dropZone.style.pointerEvents = "none";
        fileNameDisplay.textContent = "";
    }

    dropZone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            onFileSelected(fileInput.files[0]);
        }
    });

    // Drag-and-drop
    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            onFileSelected(e.dataTransfer.files[0]);
        }
    });

    // --- Error display ---
    function showError(message) {
        errorMessage.textContent = message;
        errorBox.hidden = false;
    }

    function hideError() {
        errorBox.hidden = true;
    }

    // --- Form submission ---
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        hideError();

        if (!selectedFile) {
            showError("Please select an audio file first.");
            return;
        }

        // Build form data
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("onset_threshold", onsetSlider.value);
        formData.append("frame_threshold", frameSlider.value);
        formData.append("min_note_length", noteLenSlider.value);
        formData.append("abc", document.getElementById("abc-checkbox").checked);

        // Show processing dialog
        submitBtn.disabled = true;
        dialog.showModal();

        try {
            const response = await fetch("/api/transcribe", {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || `Server error (${response.status})`);
            }

            const result = await response.json();

            // Redirect to result page
            window.location.href = `/result.html?job=${result.job_id}`;

        } catch (err) {
            dialog.close();
            submitBtn.disabled = false;
            showError(`Transcription failed: ${err.message}`);
        }
    });
})();

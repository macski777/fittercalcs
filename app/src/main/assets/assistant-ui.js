/* FitterCalcs Ask — floating document assistant UI.
   Self-contained: creates the button, panel and admin library view. */
(function () {
  "use strict";

  if (document.getElementById("fcaPanel")) return;

  var state = {
    status: null,
    user: null,
    open: false,
    busy: false,
    messages: [],
    controller: null,
    view: "chat",
    thinking: false,
    streamText: null,
    autoRead: false,
    speakingButton: null,
    speechUtterance: null,
    speechToken: 0,
    speechAudio: null,
    speechUrl: null,
    lastSpeech: null,
    pageSource: null,
    pageNumber: 1,
    pageZoomed: false,
    recognition: null,
    listening: false,
    dictationBase: ""
  };

  var THINK_KEY = "fc-assistant:thinking";
  var AUTO_KEY = "fc-assistant:autoread";
  var CHAT_PREFIX = "fc-assistant:chat:";
  var MAX_FILE = 60 * 1024 * 1024;

  var icons = {
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.2 9.2 0 0 1-4.1-1L3 20l1.3-4.2A8.4 8.4 0 1 1 21 11.5Z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 2 11 13"/><path d="m22 2-7 20-4-9-9-4Z"/></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
    speaker: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5"/></svg>',
    upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>',
    doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h8"/></svg>'
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function inlineMarkup(text) {
    var html = text;
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    html = html.replace(/\[(\d{1,2})\]/g, function (_, n) {
      return '<button type="button" class="fca-cite" data-n="' + n + '">' + n + "</button>";
    });
    return html;
  }

  function markdown(text) {
    if (!text) return "";
    var source = escapeHtml(text).replace(/\r\n/g, "\n");
    var lines = source.split("\n");
    var out = "";
    var paragraph = [];
    var list = "";
    var code = false;
    var codeLines = [];
    var table = null;

    function flushParagraph() {
      if (paragraph.length) {
        out += "<p>" + inlineMarkup(paragraph.join(" ")) + "</p>";
        paragraph = [];
      }
    }
    function closeList() {
      if (list) {
        out += "</" + list + ">";
        list = "";
      }
    }
    function closeTable() {
      if (!table) return;
      var rows = table;
      table = null;
      if (!rows.length) return;
      out += '<div class="fca-table-wrap"><table>';
      rows.forEach(function (cells, index) {
        var tag = index === 0 ? "th" : "td";
        out += "<tr>";
        cells.forEach(function (cell) {
          out += "<" + tag + ">" + inlineMarkup(cell) + "</" + tag + ">";
        });
        out += "</tr>";
      });
      out += "</table></div>";
    }
    function flushAll() {
      flushParagraph();
      closeList();
      closeTable();
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var trimmed = line.trim();
      if (trimmed.indexOf("```") === 0) {
        flushAll();
        if (code) {
          out += "<pre><code>" + codeLines.join("\n") + "</code></pre>";
          codeLines = [];
          code = false;
        } else {
          code = true;
        }
        continue;
      }
      if (code) {
        codeLines.push(line);
        continue;
      }
      if (!trimmed) {
        flushParagraph();
        closeList();
        closeTable();
        continue;
      }
      if (/^#{1,4}\s+/.test(trimmed)) {
        flushAll();
        out += "<h3>" + inlineMarkup(trimmed.replace(/^#{1,4}\s+/, "")) + "</h3>";
        continue;
      }
      if (/^\|.*\|$/.test(trimmed)) {
        flushParagraph();
        closeList();
        var cells = trimmed.replace(/^\||\|$/g, "").split("|").map(function (cell) {
          return cell.trim();
        });
        var separator = cells.every(function (cell) {
          return /^:?-{2,}:?$/.test(cell);
        });
        if (separator) continue;
        if (!table) table = [];
        table.push(cells);
        continue;
      }
      closeTable();
      if (/^\s*[-*•]\s+/.test(line)) {
        flushParagraph();
        if (list !== "ul") {
          closeList();
          out += "<ul>";
          list = "ul";
        }
        out += "<li>" + inlineMarkup(line.replace(/^\s*[-*•]\s+/, "")) + "</li>";
        continue;
      }
      if (/^\s*\d+[.)]\s+/.test(line)) {
        flushParagraph();
        if (list !== "ol") {
          closeList();
          out += "<ol>";
          list = "ol";
        }
        out += "<li>" + inlineMarkup(line.replace(/^\s*\d+[.)]\s+/, "")) + "</li>";
        continue;
      }
      closeList();
      paragraph.push(trimmed);
    }
    flushAll();
    if (code && codeLines.length) {
      out += "<pre><code>" + codeLines.join("\n") + "</code></pre>";
    }
    return out || "<p></p>";
  }

  function fetchJson(method, path, body) {
    var options = {
      method: method,
      credentials: "same-origin",
      cache: "no-store",
      headers: {}
    };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var message = (data && data.error) || ("Request failed (" + response.status + ")");
          var error = new Error(message);
          error.status = response.status;
          throw error;
        }
        return data;
      });
    });
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function chatKey() {
    return CHAT_PREFIX + ((state.user && state.user.username) || "unknown");
  }

  /* ------------------------------------------------------------------ */
  /* Voice: read aloud and dictation                                    */
  /* ------------------------------------------------------------------ */

  function hasNativeVoice() {
    try {
      return !!(window.FCVoice && typeof window.FCVoice.speak === "function");
    } catch (error) {
      return false;
    }
  }

  function hasWebTts() {
    return !!(window.speechSynthesis && typeof window.SpeechSynthesisUtterance !== "undefined");
  }

  function ttsAvailable() {
    return hasNativeVoice() || hasWebTts() || serverTtsAvailable();
  }

  function serverTtsAvailable() {
    return !!(state.status && state.status.tts);
  }

  function updateVoiceUi() {
    var available = ttsAvailable();
    if (autoReadLabel) autoReadLabel.style.display = available ? "" : "none";
    if (sourceSpeak) sourceSpeak.style.display = available ? "" : "none";
  }

  function speechRecognitionClass() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function dictationAvailable() {
    return hasNativeVoice() || !!speechRecognitionClass();
  }

  function speechText(text) {
    var plain = String(text || "")
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/`([^`]*)`/g, "$1")
      .replace(/\[(\d{1,2})\]/g, "")
      .replace(/^#{1,6}\s*/gm, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*\n]+)\*/g, "$1")
      .replace(/^\s*[-*•]\s+/gm, "")
      .replace(/\s+/g, " ")
      .trim();
    if (plain.length > 3800) plain = plain.slice(0, 3800) + ".";
    return plain;
  }

  function showListen(message, kind) {
    if (!listenEl) return;
    listenEl.hidden = !message;
    listenEl.className = "fca-listen" + (kind ? " fca-listen-" + kind : "");
    if (listenText) listenText.textContent = message || "";
  }

  function hideListenSoon() {
    setTimeout(function () {
      if (!state.listening) showListen("", "");
    }, 1200);
  }

  function setListening(on) {
    state.listening = !!on;
    if (micBtn) {
      micBtn.classList.toggle("on", !!on);
      micBtn.setAttribute("aria-pressed", on ? "true" : "false");
      micBtn.title = on ? "Stop dictation" : "Dictate a question";
    }
    if (on) showListen("Listening… speak your question", "listening");
  }

  function resetSpeaking(button) {
    var target = button || state.speakingButton;
    if (target) {
      target.classList.remove("on");
      var label = target.querySelector("span");
      if (label) label.textContent = target.getAttribute("data-label") || "Read aloud";
    }
    state.speakingButton = null;
    state.speechUtterance = null;
  }

  function stopSpeaking() {
    state.speechToken = (state.speechToken || 0) + 1;
    state.lastSpeech = null;
    try {
      if (hasNativeVoice() && typeof window.FCVoice.stopSpeaking === "function") {
        window.FCVoice.stopSpeaking();
      }
    } catch (error) {}
    if (hasWebTts()) {
      try {
        window.speechSynthesis.cancel();
      } catch (error) {}
    }
    if (state.speechAudio) {
      try {
        state.speechAudio.pause();
        state.speechAudio.currentTime = 0;
      } catch (error) {}
      state.speechAudio = null;
    }
    if (state.speechUrl) {
      try {
        URL.revokeObjectURL(state.speechUrl);
      } catch (error) {}
      state.speechUrl = null;
    }
    resetSpeaking(null);
  }

  function markSpeaking(button) {
    state.speakingButton = button || null;
    if (button) {
      button.classList.add("on");
      var label = button.querySelector("span");
      if (label) label.textContent = "Stop";
    }
  }

  function speakServer(text, button, token) {
    state.lastSpeech = null;
    markSpeaking(button);
    showListen("Preparing voice…", "listening");
    fetch("/api/assistant/speech", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text })
    }).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          throw new Error(data.error || ("Speech failed (" + response.status + ")"));
        });
      }
      return response.blob();
    }).then(function (blob) {
      if (token !== state.speechToken) return;
      var url = URL.createObjectURL(blob);
      var audio = new Audio(url);
      state.speechAudio = audio;
      state.speechUrl = url;
      audio.onended = function () {
        if (state.speechUrl === url) {
          try { URL.revokeObjectURL(url); } catch (error) {}
          state.speechUrl = null;
        }
        state.speechAudio = null;
        resetSpeaking(button);
        showListen("", "");
      };
      audio.onerror = function () {
        if (state.speechUrl === url) {
          try { URL.revokeObjectURL(url); } catch (error) {}
          state.speechUrl = null;
        }
        state.speechAudio = null;
        resetSpeaking(button);
        showListen("Speech playback failed.", "error");
      };
      var played = audio.play();
      if (played && played.catch) {
        played.catch(function () {
          resetSpeaking(button);
          showListen("Tap Read aloud again to allow audio.", "error");
        });
      }
      showListen("", "");
    }).catch(function (error) {
      if (token !== state.speechToken) return;
      resetSpeaking(button);
      showListen(error.message || "Speech failed.", "error");
    });
  }

  function speakText(text, button) {
    var clean = speechText(text);
    if (!clean) return;
    stopSpeaking();
    var token = (state.speechToken || 0) + 1;
    state.speechToken = token;
    state.lastSpeech = { text: clean, button: button, token: token };
    if (hasNativeVoice()) {
      markSpeaking(button);
      try {
        window.FCVoice.speak(clean);
      } catch (error) {
        if (serverTtsAvailable()) {
          speakServer(clean, button, token);
        } else {
          state.lastSpeech = null;
          resetSpeaking(button);
          showListen("Text to speech is not available.", "error");
        }
      }
      return;
    }
    if (hasWebTts()) {
      try {
        var utterance = new SpeechSynthesisUtterance(clean);
        utterance.lang = "en-AU";
        utterance.rate = 1;
        utterance.pitch = 1;
        var voices = window.speechSynthesis.getVoices() || [];
        var voice = null;
        for (var i = 0; i < voices.length; i++) {
          if (/^en[-_]AU/i.test(voices[i].lang)) {
            voice = voices[i];
            break;
          }
        }
        if (!voice) {
          for (var j = 0; j < voices.length; j++) {
            if (/^en[-_]/i.test(voices[j].lang)) {
              voice = voices[j];
              break;
            }
          }
        }
        if (voice) utterance.voice = voice;
        utterance.onend = function () {
          if (token !== state.speechToken) return;
          state.lastSpeech = null;
          resetSpeaking(button);
        };
        utterance.onerror = function () {
          if (token !== state.speechToken) return;
          if (serverTtsAvailable()) {
            speakServer(clean, button, token);
            return;
          }
          state.lastSpeech = null;
          resetSpeaking(button);
          showListen("Text to speech could not read that answer.", "error");
        };
        state.speechUtterance = utterance;
        markSpeaking(button);
        window.speechSynthesis.speak(utterance);
      } catch (error) {
        if (serverTtsAvailable()) {
          speakServer(clean, button, token);
          return;
        }
        state.lastSpeech = null;
        resetSpeaking(button);
        showListen("Text to speech is not available in this app.", "error");
      }
      return;
    }
    if (serverTtsAvailable()) {
      speakServer(clean, button, token);
      return;
    }
    state.lastSpeech = null;
    showListen("Text to speech is not available in this app.", "error");
  }

  function toggleSpeakText(text, button) {
    if (button && state.speakingButton === button) {
      stopSpeaking();
      return;
    }
    speakText(text, button);
  }

  function stopDictation() {
    if (state.listening && hasNativeVoice() && typeof window.FCVoice.stopDictation === "function") {
      try {
        window.FCVoice.stopDictation();
      } catch (error) {}
    }
    if (state.recognition) {
      try {
        state.recognition.stop();
      } catch (error) {}
      state.recognition = null;
    }
    setListening(false);
    hideListenSoon();
  }

  function applyDictation(text, isFinal) {
    var clean = String(text || "").trim();
    var base = state.dictationBase || "";
    inputEl.value = base ? (base + " " + clean).trim() : clean;
    autoResize();
    sendBtn.disabled = state.busy || !inputEl.value.trim();
    if (isFinal) {
      setListening(false);
      hideListenSoon();
      inputEl.focus();
    }
  }

  function startBrowserDictation() {
    var Recognition = speechRecognitionClass();
    if (!Recognition) {
      showListen("Dictation isn't available in this app. Install the updated FitterCalcs APK or use Chrome.", "error");
      return;
    }
    try {
      var recognition = new Recognition();
      recognition.lang = "en-AU";
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.onstart = function () { setListening(true); };
      recognition.onresult = function (event) {
        var transcript = "";
        var final = false;
        for (var i = 0; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript + " ";
          if (event.results[i].isFinal) final = true;
        }
        applyDictation(transcript.trim(), final);
      };
      recognition.onerror = function (event) {
        var message = "Dictation stopped.";
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          message = "Microphone permission is required.";
        } else if (event.error === "no-speech") {
          message = "I didn't hear anything. Tap the mic and try again.";
        } else if (event.error === "network") {
          message = "Speech recognition needs an internet connection.";
        }
        showListen(message, "error");
        setListening(false);
        state.recognition = null;
      };
      recognition.onend = function () {
        setListening(false);
        state.recognition = null;
        hideListenSoon();
      };
      state.recognition = recognition;
      state.dictationBase = inputEl.value.trim();
      setListening(true);
      recognition.start();
    } catch (error) {
      state.recognition = null;
      setListening(false);
      showListen("Dictation could not start.", "error");
    }
  }

  function toggleDictation() {
    if (state.listening) {
      stopDictation();
      return;
    }
    if (state.busy) return;
    stopSpeaking();
    state.dictationBase = inputEl.value.trim();
    if (hasNativeVoice() && typeof window.FCVoice.startDictation === "function") {
      setListening(true);
      showListen("Starting the microphone…", "listening");
      try {
        window.FCVoice.startDictation();
      } catch (error) {
        setListening(false);
        showListen("Dictation could not start.", "error");
      }
      return;
    }
    startBrowserDictation();
  }

  window.FCVoiceOnDone = function (status, message) {
    if (status === "error") {
      var fallback = state.lastSpeech;
      if (fallback && fallback.token === state.speechToken && serverTtsAvailable()) {
        state.lastSpeech = null;
        speakServer(fallback.text, fallback.button, fallback.token);
        return;
      }
      state.lastSpeech = null;
      if (message) showListen(message, "error");
      resetSpeaking(null);
    } else if (status === "done") {
      state.lastSpeech = null;
      resetSpeaking(null);
    }
  };

  window.FCVoiceOnDictation = function (status, message) {
    if (status === "listening") {
      setListening(true);
      showListen("Listening… speak your question", "listening");
      return;
    }
    if (status === "processing") {
      showListen("Working out what you said…", "listening");
      return;
    }
    setListening(false);
    if (status === "error") showListen(message || "Dictation stopped.", "error");
    else hideListenSoon();
  };

  window.FCVoiceOnText = function (text, isFinal) {
    applyDictation(text, !!isFinal);
  };

  function notifyNativeOverlay() {
    try {
      if (hasNativeVoice() && typeof window.FCVoice.setOverlay === "function") {
        window.FCVoice.setOverlay(!!state.open);
      }
    } catch (error) {}
  }

  window.FCAssistantBack = function () {
    if (pageView && !pageView.hidden) {
      closePdfPage();
      return true;
    }
    if (sourceWrap && !sourceWrap.hidden) {
      closeSource();
      return true;
    }
    if (state.open) {
      if (state.view === "library") showView("chat");
      else closePanel();
      return true;
    }
    return false;
  };

  /* ------------------------------------------------------------------ */
  /* DOM                                                                */
  /* ------------------------------------------------------------------ */

  var root = document.createElement("div");
  root.id = "fcaRoot";
  root.innerHTML =
    '<button id="fcaBtn" type="button" aria-label="Ask Stillo" title="Ask Stillo" aria-expanded="false" hidden>' +
      '<img class="fca-fab-icon" src="stillo.png" alt="" />' +
      '<span class="fca-fab-label">Ask Stillo</span>' +
    "</button>" +
    '<div id="fcaBackdrop"></div>' +
    '<section id="fcaPanel" role="dialog" aria-modal="true" aria-labelledby="fcaTitle" hidden>' +
      '<header class="fca-head">' +
        '<button type="button" class="fca-icon" id="fcaBack" title="Back" aria-label="Back" hidden>' + icons.back + "</button>" +
        '<div class="fca-head-titles">' +
          '<div class="fca-title" id="fcaTitle"><img class="fca-title-icon" src="stillo.png" alt="" /> <span class="fca-dot"></span>Ask Stillo</div>' +
          '<div class="fca-sub" id="fcaSub">Searching the documents on this PC</div>' +
        "</div>" +
        '<div class="fca-head-actions">' +
          '<button type="button" class="fca-icon" id="fcaNew" title="New chat" aria-label="New chat">' + icons.plus + "</button>" +
          '<button type="button" class="fca-icon" id="fcaGear" title="Document library" aria-label="Document library" hidden>' + icons.gear + "</button>" +
          '<button type="button" class="fca-icon" id="fcaClose" title="Close" aria-label="Close">' + icons.close + "</button>" +
        "</div>" +
      "</header>" +
      '<div class="fca-body">' +
        '<div class="fca-chat" id="fcaChat">' +
          '<div class="fca-messages" id="fcaMessages" aria-live="polite"></div>' +
          '<div class="fca-empty" id="fcaEmpty">' +
            '<div class="fca-empty-icon"><img src="stillo.png" alt="Stillo" /></div>' +
            '<h2>Ask Stillo</h2>' +
            '<p>Answers come only from the documents in this PC\'s library. Every answer shows the clause and page it came from.</p>' +
            '<div class="fca-suggest" id="fcaSuggest">' +
              '<button type="button" data-q="What are the hydrant water supply requirements in AS 2419.1?">What does AS 2419.1 require for hydrant water supply?</button>' +
              '<button type="button" data-q="What does AS 1851 require for monthly hose reel pumpset service?">What is required for monthly hose reel pump service?</button>' +
              '<button type="button" data-q="What are the sprinkler system design requirements in AS 2118.1?">What does AS 2118.1 require for sprinkler systems?</button>' +
            "</div>" +
          "</div>" +
        "</div>" +
        '<div class="fca-library" id="fcaLibrary" hidden>' +
          '<div class="fca-lib-actions">' +
            '<button type="button" class="fca-btn primary" id="fcaAdd">' + icons.upload + " Add files</button>" +
            '<button type="button" class="fca-btn" id="fcaRescan">' + icons.refresh + " Rescan folder</button>" +
            '<input type="file" id="fcaFile" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.html,.htm,.eml,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp" hidden>' +
          "</div>" +
          '<div class="fca-drop" id="fcaDrop">' + icons.upload + "<span>Drop documents here, or use Add files.</span></div>" +
          '<div class="fca-job" id="fcaJob" hidden><span id="fcaJobText"></span><div class="fca-progress"><i id="fcaProgress"></i></div></div>' +
          '<div class="fca-doc-list" id="fcaDocs"></div>' +
        "</div>" +
      "</div>" +
      '<div class="fca-listen" id="fcaListen" hidden><span class="fca-listen-dot"></span><span id="fcaListenText"></span></div>' +
      '<form class="fca-composer" id="fcaForm">' +
        '<textarea id="fcaInput" rows="1" maxlength="2000" placeholder="Ask about the documents…" enterkeyhint="send" aria-label="Question"></textarea>' +
        '<button type="button" class="fca-mic" id="fcaMic" title="Dictate a question" aria-label="Dictate a question" aria-pressed="false">' + icons.mic + "</button>" +
        '<button type="submit" class="fca-send" id="fcaSend" title="Send" aria-label="Send">' + icons.send + "</button>" +
        '<button type="button" class="fca-stop" id="fcaStop" title="Stop" aria-label="Stop" hidden>' + icons.stop + "</button>" +
      "</form>" +
      '<div class="fca-foot" id="fcaFoot">' +
        "<span>Answers come only from the documents on this PC. Check the current Standard.</span>" +
        '<div class="fca-toggles">' +
          '<label class="fca-think" id="fcaAutoReadLabel"><input type="checkbox" class="fca-switch" id="fcaAutoRead"><span>Read answers</span></label>' +
          '<label class="fca-think" id="fcaThinkLabel"><input type="checkbox" class="fca-switch" id="fcaThink"><span>Deep reasoning</span></label>' +
        "</div>" +
      "</div>" +
      '<div id="fcaSource" hidden>' +
        '<div class="fca-source-card" role="dialog" aria-modal="true" aria-labelledby="fcaSourceTitle">' +
          '<div class="fca-source-head">' +
            '<div class="fca-source-title" id="fcaSourceTitle">Source</div>' +
            '<button type="button" class="fca-icon" id="fcaSourceClose" title="Close" aria-label="Close">' + icons.close + "</button>" +
          "</div>" +
          '<div class="fca-source-meta" id="fcaSourceMeta"></div>' +
          '<div class="fca-source-hint">Exact passage used for this answer <span class="fca-source-swipe">· Swipe right to go back</span></div>' +
          '<pre class="fca-source-text" id="fcaSourceText"></pre>' +
          '<div class="fca-source-actions">' +
            '<button type="button" class="fca-btn primary" id="fcaSourcePdf">Open PDF at page</button>' +
            '<button type="button" class="fca-btn" id="fcaSourceSpeak" data-label="Read aloud">' + icons.speaker + "<span>Read aloud</span></button>" +
            '<button type="button" class="fca-btn" id="fcaSourceCopy" disabled>Copy text</button>' +
          "</div>" +
          '<div class="fca-page-view" id="fcaPageView" hidden>' +
            '<div class="fca-page-head">' +
              '<div class="fca-page-title" id="fcaPageTitle">PDF page</div>' +
              '<button type="button" class="fca-icon" id="fcaPageClose" title="Close" aria-label="Close">' + icons.close + "</button>" +
            "</div>" +
            '<div class="fca-page-tools">' +
              '<button type="button" class="fca-btn" id="fcaPagePrev">Prev</button>' +
              '<button type="button" class="fca-btn" id="fcaPageNext">Next</button>' +
              '<button type="button" class="fca-btn" id="fcaPageZoom">Zoom</button>' +
            "</div>" +
            '<div class="fca-page-scroll" id="fcaPageScroll">' +
              '<img id="fcaPageImage" alt="PDF page" />' +
              '<div class="fca-page-status" id="fcaPageStatus">Rendering…</div>' +
            "</div>" +
            '<div class="fca-page-actions">' +
              '<a class="fca-btn" id="fcaPageOriginal" href="#" target="_blank" rel="noopener">Open original PDF</a>' +
              '<button type="button" class="fca-btn primary" id="fcaPageBack">Back to text</button>' +
            "</div>" +
          "</div>" +
        "</div>" +
      "</div>" +
    "</section>";
  document.body.appendChild(root);

  var btn = document.getElementById("fcaBtn");
  var panel = document.getElementById("fcaPanel");
  var backdrop = document.getElementById("fcaBackdrop");
  var closeBtn = document.getElementById("fcaClose");
  var newBtn = document.getElementById("fcaNew");
  var gearBtn = document.getElementById("fcaGear");
  var backBtn = document.getElementById("fcaBack");
  var titleEl = document.getElementById("fcaTitle");
  var subEl = document.getElementById("fcaSub");
  var chatEl = document.getElementById("fcaChat");
  var messagesEl = document.getElementById("fcaMessages");
  var emptyEl = document.getElementById("fcaEmpty");
  var suggestEl = document.getElementById("fcaSuggest");
  var libraryEl = document.getElementById("fcaLibrary");
  var docsEl = document.getElementById("fcaDocs");
  var formEl = document.getElementById("fcaForm");
  var inputEl = document.getElementById("fcaInput");
  var sendBtn = document.getElementById("fcaSend");
  var stopBtn = document.getElementById("fcaStop");
  var footEl = document.getElementById("fcaFoot");
  var thinkEl = document.getElementById("fcaThink");
  var thinkLabel = document.getElementById("fcaThinkLabel");
  var autoReadEl = document.getElementById("fcaAutoRead");
  var autoReadLabel = document.getElementById("fcaAutoReadLabel");
  var micBtn = document.getElementById("fcaMic");
  var listenEl = document.getElementById("fcaListen");
  var listenText = document.getElementById("fcaListenText");
  var addBtn = document.getElementById("fcaAdd");
  var rescanBtn = document.getElementById("fcaRescan");
  var fileEl = document.getElementById("fcaFile");
  var dropEl = document.getElementById("fcaDrop");
  var jobEl = document.getElementById("fcaJob");
  var jobTextEl = document.getElementById("fcaJobText");
  var progressEl = document.getElementById("fcaProgress");
  var sourceWrap = document.getElementById("fcaSource");
  var sourceTitle = document.getElementById("fcaSourceTitle");
  var sourceMeta = document.getElementById("fcaSourceMeta");
  var sourceText = document.getElementById("fcaSourceText");
  var sourcePdf = document.getElementById("fcaSourcePdf");
  var sourceCopy = document.getElementById("fcaSourceCopy");
  var sourceSpeak = document.getElementById("fcaSourceSpeak");
  var sourceClose = document.getElementById("fcaSourceClose");
  var pageView = document.getElementById("fcaPageView");
  var pageTitle = document.getElementById("fcaPageTitle");
  var pageImage = document.getElementById("fcaPageImage");
  var pageScroll = document.getElementById("fcaPageScroll");
  var pageStatus = document.getElementById("fcaPageStatus");
  var pagePrev = document.getElementById("fcaPagePrev");
  var pageNext = document.getElementById("fcaPageNext");
  var pageZoom = document.getElementById("fcaPageZoom");
  var pageOriginal = document.getElementById("fcaPageOriginal");
  var pageBack = document.getElementById("fcaPageBack");
  var pageClose = document.getElementById("fcaPageClose");
  var sourceCard = sourceWrap.querySelector(".fca-source-card");
  var sourceSwipe = null;

  /* ------------------------------------------------------------------ */
  /* Status and gate                                                    */
  /* ------------------------------------------------------------------ */

  function updateSub() {
    if (!state.status) return;
    if (!state.status.configured) {
      subEl.textContent = "DeepSeek key not configured";
      return;
    }
    var docs = state.status.docs || 0;
    var pages = state.status.pages || 0;
    subEl.textContent = docs
      ? docs + " document" + (docs === 1 ? "" : "s") + " · " + pages.toLocaleString() + " pages"
      : "No documents indexed yet";
  }

  function showButton(show) {
    btn.hidden = !show;
    if (!show) closePanel();
  }

  function loadStatus() {
    return fetch("/api/assistant/status", {
      credentials: "same-origin",
      cache: "no-store"
    }).then(function (response) {
      if (response.status === 401) {
        state.status = null;
        showButton(false);
        return null;
      }
      if (!response.ok) {
        showButton(false);
        return null;
      }
      return response.json().then(function (data) {
        state.status = data;
        state.user = data.user ? { username: data.user } : state.user;
        if (!data.allowed) {
          showButton(false);
          return null;
        }
        updateSub();
        gearBtn.hidden = !data.admin;
        showButton(true);
        updateVoiceUi();
        if (state.open && !state.busy) renderMessages();
        return data;
      });
    }).catch(function () {
      showButton(false);
    });
  }

  function gateChanged() {
    var gate = document.getElementById("accountGate");
    if (!gate) return;
    if (!gate.hidden) {
      state.status = null;
      showButton(false);
    } else {
      loadStatus();
    }
  }

  var gateEl = document.getElementById("accountGate");
  if (gateEl && window.MutationObserver) {
    new MutationObserver(gateChanged).observe(gateEl, {
      attributes: true,
      attributeFilter: ["hidden"]
    });
  }
  setTimeout(gateChanged, 350);
  setTimeout(gateChanged, 1200);
  window.addEventListener("focus", gateChanged);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) gateChanged();
  });

  /* ------------------------------------------------------------------ */
  /* Chat rendering                                                     */
  /* ------------------------------------------------------------------ */

  function sourceHref(source) {
    var url = "/api/assistant/file/" + encodeURIComponent(source.doc_id);
    var isPdf = /\.pdf$/i.test(source.filename || "");
    var page = source.page || 1;
    if (isPdf && page) url += "#page=" + encodeURIComponent(page);
    return url;
  }

  function sourceLabel(source) {
    var bits = [];
    if (source.section) bits.push(source.section);
    var page = source.printed_page || source.page;
    if (page) bits.push("p. " + page);
    return bits.join(" · ");
  }

  function buildSources(message) {
    var sources = message.sources || [];
    if (!sources.length) return null;
    var cited = message.cited || [];
    if (message.refused && !cited.length) return null;
    var shown = cited.length
      ? sources.filter(function (source) { return cited.indexOf(source.n) !== -1; })
      : sources;
    if (!shown.length) shown = sources;
    var wrap = document.createElement("div");
    wrap.className = "fca-meta";
    shown.forEach(function (source) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "fca-src";
      chip.setAttribute("data-n", String(source.n));
      chip.setAttribute("data-source-id", source.id == null ? "" : String(source.id));
      chip.setAttribute("data-title", source.title || source.filename || "Document");
      chip.setAttribute("data-section", source.section || "");
      chip.setAttribute("data-page", source.page == null ? "" : String(source.page));
      chip.setAttribute("data-printed", source.printed_page == null ? "" : String(source.printed_page));
      chip.setAttribute("data-doc-id", source.doc_id || "");
      chip.setAttribute("data-filename", source.filename || "");
      chip.setAttribute("data-edition", source.edition || "");
      chip.setAttribute("data-superseded", source.superseded_by || "");
      chip.title = "Open " + (source.section || "the cited passage") + " from " + (source.title || "the document");
      var label = sourceLabel(source);
      chip.innerHTML =
        "<b>" + source.n + "</b><span>" + escapeHtml(source.title || source.filename || "Document") +
        (label ? " · " + escapeHtml(label) : "") + "</span>" +
        (source.superseded_by
          ? '<span class="fca-old" title="This is an older edition; the current reference may be ' +
            escapeHtml(source.superseded_by) + '">older</span>'
          : "");
      wrap.appendChild(chip);
    });
    return wrap;
  }

  function sourceMetaText(source) {
    var bits = [];
    if (source.edition) bits.push(source.edition);
    if (source.section) bits.push(source.section);
    var page = source.printed_page || source.page;
    if (page) bits.push("p. " + page);
    if (source.superseded_by) bits.push("older edition — current may be " + source.superseded_by);
    return bits.join(" · ");
  }

  function sourceFromData(data) {
    return {
      n: Number(data.n || 0),
      id: data.sourceId ? Number(data.sourceId) : null,
      title: data.title || "",
      section: data.section || "",
      page: data.page ? Number(data.page) : null,
      printed_page: data.printed || null,
      doc_id: data.docId || "",
      filename: data.filename || "",
      edition: data.edition || "",
      superseded_by: data.superseded || null,
      total_pages: data.total_pages ? Number(data.total_pages) : 0
    };
  }

  function sourcePdfLabel(source) {
    var isPdf = /\.pdf$/i.test(source.filename || "");
    if (!isPdf) return "Open document";
    var page = source.printed_page || source.page;
    return page ? "Open PDF at page " + page : "Open PDF";
  }

  function cleanSourceText(text) {
    return String(text || "").split("\n").filter(function (line) {
      var trimmed = line.trim();
      if (!trimmed) return true;
      if (/^[\W_]*Standards Australia[\W_]*$/i.test(trimmed)) return false;
      if (/^Get permission to copy/i.test(trimmed)) return false;
      if (/www\.saiglobal\.com\/licensing/i.test(trimmed)) return false;
      return true;
    }).join("\n").trim();
  }

  function openSource(source) {
    stopSpeaking();
    closePdfPage();
    state.source = source;
    sourceWrap.hidden = false;
    sourceCard.style.transition = "none";
    sourceCard.style.transform = "";
    sourceCard.style.opacity = "";
    sourceTitle.textContent = "[" + source.n + "] " + (source.title || "Source");
    sourceMeta.textContent = sourceMetaText(source);
    sourceText.textContent = "Loading…";
    sourceText.scrollTop = 0;
    sourcePdf.style.display =
      source.doc_id && /\.pdf$/i.test(source.filename || "") ? "" : "none";
    sourcePdf.textContent = sourcePdfLabel(source);
    sourceCopy.textContent = "Copy text";
    sourceCopy.disabled = true;
    sourceSpeak.disabled = true;
    sourceSpeak.style.display = ttsAvailable() ? "" : "none";
    if (!source.id) {
      sourceText.textContent = "Open the PDF to read this source.";
      return;
    }
    fetchJson("GET", "/api/assistant/source/" + encodeURIComponent(source.id)).then(function (data) {
      var merged = sourceFromData({
        n: source.n,
        sourceId: data.id,
        title: data.title,
        section: data.section,
        page: data.page,
        printed: data.printed_page,
        docId: data.doc_id,
        filename: data.filename,
        edition: data.edition,
        superseded: data.superseded_by,
        total_pages: data.total_pages
      });
      state.source = merged;
      sourceTitle.textContent = "[" + merged.n + "] " + (merged.title || "Source");
      sourceMeta.textContent = sourceMetaText(merged);
      var cleanText = cleanSourceText(data.text);
      sourceText.textContent = cleanText || "No text was stored for this source.";
      sourcePdf.style.display =
        merged.doc_id && /\.pdf$/i.test(merged.filename || "") ? "" : "none";
      sourcePdf.textContent = sourcePdfLabel(merged);
      sourceCopy.disabled = !cleanText;
      sourceSpeak.disabled = !cleanText || !ttsAvailable();
      sourceText.scrollTop = 0;
    }).catch(function (error) {
      sourceText.textContent = error.message;
    });
  }

  function closeSource() {
    stopSpeaking();
    closePdfPage();
    sourceWrap.hidden = true;
  }

  function openPdfPage(source) {
    if (!source || !source.doc_id || !source.page || !/\.pdf$/i.test(source.filename || "")) {
      showListen("That source is not a PDF page.", "error");
      return;
    }
    state.pageSource = source;
    state.pageNumber = Number(source.page) || 1;
    state.pageZoomed = window.innerWidth > 700;
    pageView.hidden = false;
    pageImage.classList.toggle("fca-zoom", state.pageZoomed);
    pageZoom.textContent = state.pageZoomed ? "Zoom out" : "Zoom";
    renderPdfPage();
  }

  function renderPdfPage() {
    var source = state.pageSource;
    if (!source) return;
    var page = Math.max(1, Number(state.pageNumber) || 1);
    var total = Number(source.total_pages) || 0;
    var offset = 0;
    if (source.printed_page && source.page) {
      var printedPage = parseInt(source.printed_page, 10);
      if (!isNaN(printedPage)) offset = printedPage - Number(source.page);
    }
    var printed = offset ? page + offset : null;
    pageTitle.textContent =
      (source.title || "PDF") + " — PDF page " + page +
      (printed ? " (printed p. " + printed + ")" : "");
    pageStatus.hidden = false;
    pageStatus.textContent = "Rendering…";
    pageImage.style.opacity = "0";
    pageImage.classList.toggle("fca-zoom", state.pageZoomed);
    pageZoom.textContent = state.pageZoomed ? "Zoom out" : "Zoom";
    pageImage.onload = function () {
      pageStatus.hidden = true;
      pageImage.style.opacity = "1";
    };
    pageImage.onerror = function () {
      pageStatus.hidden = false;
      pageStatus.textContent = "That page could not be rendered.";
    };
    pageImage.alt = (source.title || "PDF") + " page " + page;
    pageImage.src =
      "/api/assistant/page/" + encodeURIComponent(source.doc_id) + "/" + page + ".png";
    pagePrev.disabled = page <= 1;
    pageNext.disabled = total > 0 && page >= total;
    pageOriginal.href =
      "/api/assistant/file/" + encodeURIComponent(source.doc_id) + "#page=" + page;
    pageScroll.scrollTop = 0;
  }

  function closePdfPage() {
    pageView.hidden = true;
    state.pageSource = null;
    state.pageZoomed = false;
    pageImage.classList.remove("fca-zoom");
    pageImage.removeAttribute("src");
    pageStatus.hidden = false;
  }

  function messageRow(message) {
    var row = document.createElement("div");
    row.className = "fca-row " + (message.role === "user" ? "fca-user" : "fca-bot");
    if (message.error) row.className += " fca-error-row";
    var bubble = document.createElement("div");
    bubble.className = "fca-bubble";
    if (message.role === "user") {
      bubble.textContent = message.content;
      bubble.style.whiteSpace = "pre-wrap";
    } else {
      var text = document.createElement("div");
      text.className = "fca-text";
      text.innerHTML = markdown(message.content || (message.streaming ? "" : ""));
      if (message.streaming) {
        var cursor = document.createElement("span");
        cursor.className = "fca-cursor";
        text.appendChild(cursor);
        state.streamText = text;
      }
      bubble.appendChild(text);
      var sources = buildSources(message);
      if (sources) bubble.appendChild(sources);
      if (message.uncited && !message.refused) {
        var warn = document.createElement("div");
        warn.className = "fca-warn";
        warn.textContent = "No source was cited in this answer — check it against the documents.";
        bubble.appendChild(warn);
      }
      if (message.bad_citations) {
        var bad = document.createElement("div");
        bad.className = "fca-warn";
        bad.textContent = "The answer referred to a source that was not supplied. Treat it with caution.";
        bubble.appendChild(bad);
      }
      if (message.stopped) {
        var stopped = document.createElement("div");
        stopped.className = "fca-stopped";
        stopped.textContent = "Stopped.";
        bubble.appendChild(stopped);
      }
      if (!message.streaming && !message.error && ttsAvailable()) {
        var tools = document.createElement("div");
        tools.className = "fca-msg-tools";
        var speak = document.createElement("button");
        speak.type = "button";
        speak.className = "fca-speak";
        speak.setAttribute("data-label", "Read aloud");
        speak.title = "Read this answer aloud";
        speak.innerHTML = icons.speaker + "<span>Read aloud</span>";
        speak.addEventListener("click", function () {
          toggleSpeakText(message.content, speak);
        });
        tools.appendChild(speak);
        bubble.appendChild(tools);
      }
    }
    row.appendChild(bubble);
    return row;
  }

  function renderMessages() {
    messagesEl.innerHTML = "";
    if (!state.messages.length) {
      emptyEl.hidden = false;
      if (state.status && !state.status.configured) {
        emptyEl.querySelector("h2").textContent = "DeepSeek is not configured";
        emptyEl.querySelector("p").textContent =
          "Add DEEPSEEK_API_KEY to ~/.config/fittercalcs/assistant.env on the server, then restart FitterCalcs.";
        suggestEl.hidden = true;
      } else if (state.status && !state.status.docs) {
        emptyEl.querySelector("h2").textContent = "No documents indexed";
        emptyEl.querySelector("p").textContent =
          "An admin can add PDFs or Word files from the document library, or drop them in ~/Documents/FitterDocs on the PC.";
        suggestEl.hidden = true;
      } else {
        emptyEl.querySelector("h2").textContent = "Ask Stillo";
        emptyEl.querySelector("p").textContent =
          "Answers come only from the documents in this PC's library. Every answer shows the clause and page it came from.";
        suggestEl.hidden = false;
      }
      return;
    }
    emptyEl.hidden = true;
    state.streamText = null;
    state.messages.forEach(function (message) {
      messagesEl.appendChild(messageRow(message));
    });
    scrollToBottom();
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function updateStream(text) {
    if (!state.streamText) return;
    var cursor = state.streamText.querySelector(".fca-cursor");
    state.streamText.textContent = text;
    if (cursor) state.streamText.appendChild(cursor);
    scrollToBottom();
  }

  function saveChat() {
    if (!state.user) return;
    try {
      var messages = state.messages.filter(function (message) {
        return !message.streaming;
      }).slice(-24).map(function (message) {
        return {
          role: message.role,
          content: message.content,
          sources: message.sources || [],
          cited: message.cited || [],
          refused: !!message.refused,
          uncited: !!message.uncited,
          bad_citations: !!message.bad_citations,
          stopped: !!message.stopped
        };
      });
      localStorage.setItem(chatKey(), JSON.stringify({ messages: messages, saved: Date.now() }));
    } catch (error) {}
  }

  function loadChat() {
    state.messages = [];
    if (!state.user) return;
    try {
      var data = JSON.parse(localStorage.getItem(chatKey()) || "null");
      if (data && Array.isArray(data.messages)) {
        state.messages = data.messages.filter(function (message) {
          return message && (message.role === "user" || message.role === "assistant") &&
            typeof message.content === "string";
        }).slice(-24);
      }
    } catch (error) {}
  }

  function updateComposer() {
    sendBtn.hidden = state.busy;
    stopBtn.hidden = !state.busy;
    inputEl.disabled = state.busy;
    if (micBtn) {
      micBtn.hidden = state.busy;
      micBtn.disabled = state.busy;
    }
    sendBtn.disabled = state.busy || !inputEl.value.trim();
    if (!state.busy) {
      setTimeout(function () { inputEl.focus(); }, 20);
    }
  }

  function autoResize() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(118, inputEl.scrollHeight) + "px";
  }

  function newChat() {
    if (state.busy && state.controller) state.controller.abort();
    stopSpeaking();
    if (state.listening) stopDictation();
    state.messages = [];
    state.busy = false;
    state.controller = null;
    try { localStorage.removeItem(chatKey()); } catch (error) {}
    renderMessages();
    updateComposer();
    inputEl.focus();
  }

  function addLocalError(message) {
    state.messages.push({ role: "assistant", content: message, error: true });
    renderMessages();
    saveChat();
  }

  /* ------------------------------------------------------------------ */
  /* Streaming                                                          */
  /* ------------------------------------------------------------------ */

  function applyResult(message, result) {
    message.content = result.answer || message.content;
    message.sources = result.sources || message.sources || [];
    message.cited = result.cited || [];
    message.refused = !!result.refused;
    message.uncited = !!result.uncited;
    message.bad_citations = !!result.bad_citations;
    message.streaming = false;
    message.stopped = false;
    if (state.autoRead && state.open && !state.busy && ttsAvailable() && message.content) {
      setTimeout(function () {
        if (state.autoRead && state.open && !state.busy) speakText(message.content, null);
      }, 90);
    }
  }

  function readEventStream(response, onEvent) {
    if (!response.body || !response.body.getReader) {
      return Promise.reject(new Error("This browser cannot stream the answer."));
    }
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    function pump() {
      return reader.read().then(function (result) {
        if (result.done) return;
        buffer += decoder.decode(result.value, { stream: true });
        var cut;
        while ((cut = buffer.indexOf("\n\n")) !== -1) {
          var block = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          var data = "";
          block.split("\n").forEach(function (line) {
            if (line.indexOf("data:") === 0) data += line.slice(5).trim();
          });
          if (!data) continue;
          var event;
          try { event = JSON.parse(data); } catch (error) { continue; }
          onEvent(event);
        }
        return pump();
      });
    }
    return pump();
  }

  function send(question) {
    question = String(question || "").trim();
    if (!question || state.busy) return;
    stopSpeaking();
    if (state.listening) stopDictation();
    if (!state.status || !state.status.allowed) {
      addLocalError("This account does not have access to the document assistant.");
      return;
    }
    if (!state.status.configured) {
      addLocalError("DeepSeek is not configured yet. Add DEEPSEEK_API_KEY on the server.");
      return;
    }
    var history = state.messages
      .filter(function (message) { return !message.error && !message.streaming && message.content; })
      .slice(-8)
      .map(function (message) {
        return { role: message.role, content: message.content.slice(0, 4000) };
      });
    var userMessage = { role: "user", content: question };
    var botMessage = {
      role: "assistant", content: "", streaming: true,
      sources: [], refused: false, uncited: false, bad_citations: false
    };
    state.messages.push(userMessage, botMessage);
    state.busy = true;
    state.controller = new AbortController();
    inputEl.value = "";
    autoResize();
    renderMessages();
    updateComposer();
    saveChat();

    var controller = state.controller;
    var finished = false;
    fetch("/api/assistant/chat", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
      },
      body: JSON.stringify({
        question: question,
        history: history,
        thinking: state.thinking
      })
    }).then(function (response) {
      var type = response.headers.get("Content-Type") || "";
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          throw new Error(data.error || ("The assistant returned " + response.status + "."));
        });
      }
      if (type.indexOf("text/event-stream") === -1) {
        return response.json().then(function (data) {
          applyResult(botMessage, data);
          finished = true;
          renderMessages();
        });
      }
      return readEventStream(response, function (event) {
        if (event.sources) {
          botMessage.sources = event.sources;
          var row = messagesEl.lastElementChild;
          if (row) {
            var bubble = row.querySelector(".fca-bubble");
            var old = bubble && bubble.querySelector(".fca-meta");
            if (old) old.remove();
            var meta = buildSources(botMessage);
            if (meta && bubble) bubble.appendChild(meta);
          }
        }
        if (typeof event.text === "string") {
          botMessage.content += event.text;
          updateStream(botMessage.content);
        }
        if (event.answer !== undefined) {
          applyResult(botMessage, event);
          finished = true;
          renderMessages();
        }
        if (event.message && event.answer === undefined && !event.sources) {
          throw new Error(event.message);
        }
      });
    }).then(function () {
      if (botMessage.streaming) {
        botMessage.streaming = false;
        if (!finished) {
          botMessage.error = true;
          botMessage.content = (botMessage.content || "") +
            "\n\nThe connection closed before the answer finished.";
        }
        renderMessages();
      }
    }).catch(function (error) {
      botMessage.streaming = false;
      if (error && error.name === "AbortError") {
        botMessage.stopped = true;
        if (!botMessage.content) botMessage.content = "Stopped.";
      } else {
        botMessage.error = true;
        botMessage.content = (error && error.message) || "The assistant could not answer.";
      }
      renderMessages();
    }).then(function () {
      state.busy = false;
      state.controller = null;
      updateComposer();
      saveChat();
    });
  }

  /* ------------------------------------------------------------------ */
  /* Sources and citations                                              */
  /* ------------------------------------------------------------------ */

  messagesEl.addEventListener("click", function (event) {
    var chip = event.target.closest ? event.target.closest(".fca-src") : null;
    if (chip) {
      openSource(sourceFromData(chip.dataset));
      return;
    }
    var cite = event.target.closest ? event.target.closest(".fca-cite") : null;
    if (!cite) return;
    var n = cite.getAttribute("data-n");
    var row = cite.closest(".fca-row");
    var target = row && row.querySelector('.fca-src[data-n="' + n + '"]');
    if (target) openSource(sourceFromData(target.dataset));
  });

  /* ------------------------------------------------------------------ */
  /* Admin library                                                      */
  /* ------------------------------------------------------------------ */

  function formatSize(bytes) {
    if (!bytes && bytes !== 0) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  function showJob(text, ratio) {
    jobEl.hidden = false;
    jobTextEl.textContent = text;
    progressEl.style.width = Math.max(0, Math.min(100, Math.round(ratio * 100))) + "%";
  }

  function hideJobLater() {
    setTimeout(function () {
      jobEl.hidden = true;
      progressEl.style.width = "0%";
    }, 3500);
  }

  function pollJob(jobId) {
    var started = Date.now();
    function step() {
      return fetchJson("GET", "/api/assistant/jobs/" + encodeURIComponent(jobId)).then(function (job) {
        if (job.status === "done") {
          var result = job.result || {};
          var detail = result.files
            ? result.files + " files · " + (result.indexed || 0) + " indexed · " + (result.skipped || 0) + " unchanged"
            : "Finished";
          if (result.errors && result.errors.length) {
            detail += " · " + result.errors.length + " error" + (result.errors.length === 1 ? "" : "s");
          }
          showJob(detail, 1);
          hideJobLater();
          return result;
        }
        if (job.status === "error") {
          showJob(job.message || "Indexing failed", 1);
          throw new Error(job.message || "Indexing failed");
        }
        var ratio = job.total ? job.progress / job.total : 0.1;
        showJob((job.message || "Indexing") + (job.total ? " (" + job.progress + "/" + job.total + ")" : ""), ratio);
        if (Date.now() - started > 10 * 60 * 1000) {
          throw new Error("Indexing is taking too long. Check the server log.");
        }
        return sleep(800).then(step);
      });
    }
    return step();
  }

  function renderDocs(docs) {
    docsEl.innerHTML = "";
    if (!docs.length) {
      var empty = document.createElement("div");
      empty.className = "fca-lib-empty";
      empty.textContent = "No documents yet. Add a PDF, Word file, spreadsheet, text file or scanned page.";
      docsEl.appendChild(empty);
      return;
    }
    docs.forEach(function (doc) {
      var row = document.createElement("div");
      row.className = "fca-doc";
      var main = document.createElement("div");
      main.className = "fca-doc-main";
      var name = document.createElement("div");
      name.className = "fca-doc-name";
      name.textContent = doc.title || doc.filename;
      main.appendChild(name);
      var meta = document.createElement("div");
      meta.className = "fca-doc-meta" + (doc.status === "error" ? " error" : "");
      if (doc.status === "error") {
        meta.textContent = doc.error || "Could not index this file.";
      } else {
        meta.textContent =
          (doc.pages || 0) + " pages · " + (doc.chunks || 0) + " chunks · " +
          formatSize(doc.size);
      }
      main.appendChild(meta);
      row.appendChild(main);
      var del = document.createElement("button");
      del.type = "button";
      del.className = "fca-doc-del";
      del.title = "Remove from library";
      del.setAttribute("aria-label", "Remove " + (doc.title || doc.filename));
      del.innerHTML = icons.trash;
      del.addEventListener("click", function () {
        if (!window.confirm("Remove " + (doc.title || doc.filename) + " from the library?\n\nThe file is moved to .trash, not deleted.")) return;
        fetchJson("DELETE", "/api/assistant/docs/" + encodeURIComponent(doc.id)).then(function () {
          loadLibrary();
          loadStatus();
        }).catch(function (error) {
          showJob(error.message, 1);
        });
      });
      row.appendChild(del);
      docsEl.appendChild(row);
    });
  }

  function loadLibrary() {
    docsEl.innerHTML = '<div class="fca-lib-empty">Loading…</div>';
    return fetchJson("GET", "/api/assistant/docs").then(function (data) {
      renderDocs(data.docs || []);
    }).catch(function (error) {
      docsEl.innerHTML = "";
      var box = document.createElement("div");
      box.className = "fca-lib-empty";
      box.textContent = error.message;
      docsEl.appendChild(box);
    });
  }

  function uploadFile(file) {
    return new Promise(function (resolve, reject) {
      if (file.size > MAX_FILE) {
        reject(new Error(file.name + " is larger than 60 MB."));
        return;
      }
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/assistant/docs");
      xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
      xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
      xhr.upload.onprogress = function (event) {
        if (event.lengthComputable) {
          showJob("Uploading " + file.name, event.loaded / event.total);
        }
      };
      xhr.onload = function () {
        var data = {};
        try { data = JSON.parse(xhr.responseText || "{}"); } catch (error) {}
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(data.error || ("Upload failed (" + xhr.status + ")")));
          return;
        }
        showJob("Indexing " + data.filename, 0);
        pollJob(data.job_id).then(function () {
          loadLibrary();
          loadStatus();
          resolve();
        }).catch(reject);
      };
      xhr.onerror = function () {
        reject(new Error("Could not upload " + file.name + "."));
      };
      xhr.send(file);
    });
  }

  function uploadFiles(files) {
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return;
    addBtn.disabled = true;
    rescanBtn.disabled = true;
    var chain = Promise.resolve();
    list.forEach(function (file) {
      chain = chain.then(function () { return uploadFile(file); });
    });
    chain.catch(function (error) {
      showJob(error.message, 1);
    }).then(function () {
      addBtn.disabled = false;
      rescanBtn.disabled = false;
      fileEl.value = "";
    });
  }

  addBtn.addEventListener("click", function () { fileEl.click(); });
  fileEl.addEventListener("change", function () { uploadFiles(fileEl.files); });
  rescanBtn.addEventListener("click", function () {
    rescanBtn.disabled = true;
    addBtn.disabled = true;
    fetchJson("POST", "/api/assistant/reindex").then(function (data) {
      showJob("Scanning the folder…", 0.05);
      return pollJob(data.job_id);
    }).then(function () {
      loadLibrary();
      loadStatus();
    }).catch(function (error) {
      showJob(error.message, 1);
    }).then(function () {
      rescanBtn.disabled = false;
      addBtn.disabled = false;
    });
  });
  ["dragenter", "dragover"].forEach(function (name) {
    dropEl.addEventListener(name, function (event) {
      event.preventDefault();
      dropEl.classList.add("fca-over");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    dropEl.addEventListener(name, function (event) {
      event.preventDefault();
      dropEl.classList.remove("fca-over");
    });
  });
  dropEl.addEventListener("drop", function (event) {
    if (event.dataTransfer && event.dataTransfer.files) uploadFiles(event.dataTransfer.files);
  });

  function showView(view) {
    if (view === "library") {
      stopSpeaking();
      if (state.listening) stopDictation();
      showListen("", "");
    }
    state.view = view;
    var library = view === "library";
    chatEl.hidden = library;
    libraryEl.hidden = !library;
    formEl.hidden = library;
    footEl.hidden = library;
    backBtn.hidden = !library;
    gearBtn.hidden = library || !(state.status && state.status.admin);
    newBtn.hidden = library;
    titleEl.innerHTML = library
      ? "Document library"
      : '<img class="fca-title-icon" src="stillo.png" alt="" /> <span class="fca-dot"></span>Ask Stillo';
    subEl.textContent = library
      ? "Admin · files on this PC"
      : "";
    if (library) {
      updateSub();
      loadLibrary();
    } else {
      updateSub();
      renderMessages();
      inputEl.focus();
    }
  }

  gearBtn.addEventListener("click", function () { showView("library"); });
  backBtn.addEventListener("click", function () { showView("chat"); });

  /* ------------------------------------------------------------------ */
  /* Open / close and events                                            */
  /* ------------------------------------------------------------------ */

  function openPanel() {
    if (!state.status || !state.status.allowed) {
      loadStatus().then(function (data) {
        if (data && data.allowed) openPanel();
      });
      return;
    }
    sourceWrap.hidden = true;
    panel.hidden = false;
    backdrop.classList.add("fca-show");
    state.open = true;
    notifyNativeOverlay();
    btn.setAttribute("aria-expanded", "true");
    if (window.matchMedia("(max-width: 640px)").matches) {
      document.body.classList.add("fca-lock");
    }
    loadChat();
    showView("chat");
    updateComposer();
    updateSub();
    setTimeout(function () { inputEl.focus(); }, 60);
  }

  function closePanel() {
    if (state.busy && state.controller) state.controller.abort();
    stopSpeaking();
    if (state.listening) stopDictation();
    closeSource();
    panel.hidden = true;
    backdrop.classList.remove("fca-show");
    state.open = false;
    notifyNativeOverlay();
    document.body.classList.remove("fca-lock");
    btn.setAttribute("aria-expanded", "false");
    state.streamText = null;
  }

  btn.addEventListener("click", openPanel);
  closeBtn.addEventListener("click", closePanel);
  backdrop.addEventListener("click", closePanel);
  newBtn.addEventListener("click", newChat);
  sourceClose.addEventListener("click", closeSource);
  sourcePdf.addEventListener("click", function () {
    openPdfPage(state.source);
  });
  pagePrev.addEventListener("click", function () {
    if (state.pageNumber > 1) {
      state.pageNumber -= 1;
      renderPdfPage();
    }
  });
  pageNext.addEventListener("click", function () {
    var total = state.pageSource ? Number(state.pageSource.total_pages) || 0 : 0;
    if (!total || state.pageNumber < total) {
      state.pageNumber += 1;
      renderPdfPage();
    }
  });
  pageZoom.addEventListener("click", function () {
    state.pageZoomed = !state.pageZoomed;
    pageImage.classList.toggle("fca-zoom", state.pageZoomed);
    pageZoom.textContent = state.pageZoomed ? "Zoom out" : "Zoom";
  });
  pageBack.addEventListener("click", closePdfPage);
  pageClose.addEventListener("click", closePdfPage);
  sourceSpeak.addEventListener("click", function () {
    toggleSpeakText(sourceText.textContent, sourceSpeak);
  });
  micBtn.addEventListener("click", toggleDictation);
  sourceWrap.addEventListener("click", function (event) {
    if (event.target === sourceWrap) closeSource();
  });
  sourceCopy.addEventListener("click", function () {
    var text = sourceText.textContent;
    if (!text) return;
    function selectText() {
      try {
        var range = document.createRange();
        range.selectNodeContents(sourceText);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        sourceCopy.textContent = "Selected — copy it";
      } catch (error) {
        sourceCopy.textContent = "Copy unavailable";
      }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        sourceCopy.textContent = "Copied";
        setTimeout(function () { sourceCopy.textContent = "Copy text"; }, 1500);
      }).catch(selectText);
    } else {
      selectText();
    }
  });

  /* Android-style swipe: drag the source card right to go back. */
  sourceWrap.addEventListener("touchstart", function (event) {
    if (event.touches.length !== 1) return;
    if (event.target && event.target.closest && event.target.closest("a, button")) return;
    var touch = event.touches[0];
    sourceSwipe = {
      x: touch.clientX,
      y: touch.clientY,
      dx: 0,
      dy: 0,
      at: Date.now()
    };
    sourceCard.style.transition = "none";
  }, { passive: true });

  sourceWrap.addEventListener("touchmove", function (event) {
    if (!sourceSwipe || event.touches.length !== 1) return;
    var touch = event.touches[0];
    var dx = touch.clientX - sourceSwipe.x;
    var dy = touch.clientY - sourceSwipe.y;
    if (Math.abs(dy) > Math.abs(dx) * 0.9) {
      if (Math.abs(dy) > 10) {
        sourceSwipe = null;
        sourceCard.style.transition = "transform 160ms ease, opacity 160ms ease";
        sourceCard.style.transform = "";
        sourceCard.style.opacity = "";
      }
      return;
    }
    if (dx <= 0) return;
    if (event.cancelable) event.preventDefault();
    sourceSwipe.dx = dx;
    sourceSwipe.dy = dy;
    sourceCard.style.transform = "translateX(" + Math.min(dx, 170) + "px)";
    sourceCard.style.opacity = String(Math.max(0.55, 1 - dx / 700));
  }, { passive: false });

  function endSourceSwipe() {
    if (!sourceSwipe) return;
    var dx = sourceSwipe.dx;
    var dy = sourceSwipe.dy;
    var elapsed = Date.now() - sourceSwipe.at;
    var goBack = dx > 70 && dx > Math.abs(dy) * 1.3 && elapsed < 900;
    sourceSwipe = null;
    sourceCard.style.transition = "transform 170ms ease, opacity 170ms ease";
    if (goBack) {
      sourceCard.style.transform = "translateX(110%)";
      sourceCard.style.opacity = "0";
      setTimeout(function () {
        if (!pageView.hidden) closePdfPage();
        else closeSource();
        sourceCard.style.transition = "none";
        sourceCard.style.transform = "";
        sourceCard.style.opacity = "";
      }, 170);
    } else {
      sourceCard.style.transform = "";
      sourceCard.style.opacity = "";
      setTimeout(function () { sourceCard.style.transition = ""; }, 180);
    }
  }
  sourceWrap.addEventListener("touchend", endSourceSwipe, { passive: true });
  sourceWrap.addEventListener("touchcancel", endSourceSwipe, { passive: true });

  /* Android-style edge swipe: drag inward from either side to go back. */
  var panelSwipe = null;
  panel.addEventListener("touchstart", function (event) {
    if (event.touches.length !== 1 || !state.open || !sourceWrap.hidden) return;
    if (event.target.closest && event.target.closest("a,button,input,textarea,select")) return;
    var touch = event.touches[0];
    var edge = 30;
    var fromLeft = touch.clientX <= edge;
    var fromRight = touch.clientX >= window.innerWidth - edge;
    if (!fromLeft && !fromRight) return;
    panelSwipe = {
      x: touch.clientX,
      y: touch.clientY,
      fromLeft: fromLeft,
      fromRight: fromRight,
      dx: 0,
      dy: 0,
      at: Date.now()
    };
    panel.style.transition = "none";
  }, { passive: true });

  panel.addEventListener("touchmove", function (event) {
    if (!panelSwipe || event.touches.length !== 1) return;
    var touch = event.touches[0];
    var dx = touch.clientX - panelSwipe.x;
    var dy = touch.clientY - panelSwipe.y;
    if (Math.abs(dy) > Math.abs(dx) * 0.9) {
      panelSwipe = null;
      panel.style.transition = "";
      panel.style.transform = "";
      panel.style.opacity = "";
      return;
    }
    var inward = (panelSwipe.fromLeft && dx > 0) || (panelSwipe.fromRight && dx < 0);
    if (!inward) return;
    if (event.cancelable) event.preventDefault();
    panelSwipe.dx = dx;
    panelSwipe.dy = dy;
    var shift = panelSwipe.fromLeft ? Math.min(dx, 100) : Math.max(dx, -100);
    panel.style.transform = "translateX(" + shift + "px)";
    panel.style.opacity = String(Math.max(0.75, 1 - Math.abs(dx) / 450));
  }, { passive: false });

  function endPanelSwipe() {
    if (!panelSwipe) return;
    var swipe = panelSwipe;
    panelSwipe = null;
    var back = (swipe.fromLeft && swipe.dx > 70) || (swipe.fromRight && swipe.dx < -70);
    if (back) {
      panel.style.transition = "transform 140ms ease, opacity 140ms ease";
      panel.style.transform = swipe.fromLeft ? "translateX(460px)" : "translateX(-460px)";
      panel.style.opacity = "0";
      setTimeout(function () {
        panel.style.transition = "";
        panel.style.transform = "";
        panel.style.opacity = "";
        if (window.FCAssistantBack) window.FCAssistantBack();
      }, 140);
    } else {
      panel.style.transition = "transform 140ms ease, opacity 140ms ease";
      panel.style.transform = "";
      panel.style.opacity = "";
      setTimeout(function () { panel.style.transition = ""; }, 160);
    }
  }
  panel.addEventListener("touchend", endPanelSwipe, { passive: true });
  panel.addEventListener("touchcancel", endPanelSwipe, { passive: true });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (!sourceWrap.hidden) {
      closeSource();
      event.preventDefault();
      return;
    }
    if (state.open) {
      if (state.view === "library") showView("chat");
      else closePanel();
    }
  });
  window.addEventListener("pagehide", function () {
    if (state.controller) state.controller.abort();
  });

  formEl.addEventListener("submit", function (event) {
    event.preventDefault();
    send(inputEl.value);
  });
  inputEl.addEventListener("input", function () {
    autoResize();
    sendBtn.disabled = state.busy || !inputEl.value.trim();
  });
  inputEl.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send(inputEl.value);
    }
  });
  stopBtn.addEventListener("click", function () {
    if (state.controller) state.controller.abort();
  });
  suggestEl.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("button[data-q]") : null;
    if (!button) return;
    inputEl.value = button.getAttribute("data-q");
    autoResize();
    send(inputEl.value);
  });

  try {
    state.thinking = localStorage.getItem(THINK_KEY) === "1";
  } catch (error) {}
  thinkEl.checked = state.thinking;
  if (thinkLabel) thinkLabel.classList.toggle("on", state.thinking);
  thinkEl.addEventListener("change", function () {
    state.thinking = !!thinkEl.checked;
    if (thinkLabel) thinkLabel.classList.toggle("on", state.thinking);
    try { localStorage.setItem(THINK_KEY, state.thinking ? "1" : "0"); } catch (error) {}
  });

  try {
    state.autoRead = localStorage.getItem(AUTO_KEY) === "1";
  } catch (error) {}
  if (autoReadEl) {
    autoReadEl.checked = state.autoRead;
    if (autoReadLabel) autoReadLabel.classList.toggle("on", state.autoRead);
    autoReadEl.addEventListener("change", function () {
      state.autoRead = !!autoReadEl.checked;
      if (autoReadLabel) autoReadLabel.classList.toggle("on", state.autoRead);
      try { localStorage.setItem(AUTO_KEY, state.autoRead ? "1" : "0"); } catch (error) {}
      if (!state.autoRead) stopSpeaking();
    });
  }
  if (!ttsAvailable()) {
    if (autoReadLabel) autoReadLabel.style.display = "none";
    if (sourceSpeak) sourceSpeak.style.display = "none";
  }
  updateVoiceUi();
  if (hasWebTts()) {
    try { window.speechSynthesis.getVoices(); } catch (error) {}
  }

  updateComposer();
  gateChanged();
  notifyNativeOverlay();
})();

window.createDialoguePresentation = function(helpers) {
var renderAvatarImage = helpers.renderAvatarImage;
var formatMsgText = helpers.formatMsgText;
var getTypewriterDelay = helpers.getTypewriterDelay;
var scrollChatToBottom = helpers.scrollChatToBottom;
var _typewriterAbort = null;
/* Shared speaker-aware presentation for all games, live turns and history. */
function portraitButton(name, src) {
  var button = document.createElement("button");
  button.type = "button";
  button.className = "speaker-portrait";
  button.title = name;
  button.setAttribute("aria-label", "View portrait of " + name);
  var valid = typeof src === "string" && src.indexOf("/img/") === 0 && src.indexOf("..") < 0;
  if (valid && src !== "/img/avatars/persona_default.svg") {
    var img = renderAvatarImage(button, src, name);
    img.addEventListener("error", function(){
      button.textContent = speakerInitials(name);
      button.onclick = function(){ openPortrait(name, null, button); };
    }, { once: true });
  } else button.textContent = speakerInitials(name);
  button.onclick = function(){ openPortrait(name, valid ? src : null, button); };
  return button;
}

function speakerInitials(name) {
  return name === "Unknown voice" ? "?" : String(name).split(/\s+/).slice(0, 2).map(function(p){ return Array.from(p)[0] || ""; }).join("").toUpperCase();
}

function openPortrait(name, src, opener) {
  var dialog = document.getElementById("portrait-viewer");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "portrait-viewer";
    dialog.setAttribute("aria-labelledby", "portrait-viewer-name");
    dialog.innerHTML = '<button type="button" class="portrait-close" aria-label="Close portrait">&times;</button><div class="portrait-full"></div><h2 id="portrait-viewer-name"></h2>';
    document.body.appendChild(dialog);
    dialog.querySelector("button").onclick = function(){ dialog.close(); };
    dialog.addEventListener("click", function(e){ if(e.target === dialog) dialog.close(); });
    dialog.addEventListener("close", function(){ if(dialog._opener && dialog._opener.isConnected) dialog._opener.focus(); });
  }
  dialog._opener = opener;
  dialog.querySelector("h2").textContent = name;
  var full = dialog.querySelector(".portrait-full");
  full.textContent = "";
  if (src && src !== "/img/avatars/persona_default.svg") {
    var image = renderAvatarImage(full, src, name);
    image.onerror = function(){ full.textContent = speakerInitials(name); };
  } else {
    full.textContent = speakerInitials(name);
    var note = document.createElement("p");
    note.className = "portrait-unavailable";
    note.textContent = "No portrait available yet";
    full.appendChild(note);
  }
  dialog.showModal();
}

function renderDialogueTurn(row, text, segments, animate) {
  row.classList.add("story-turn");
  var blocks = Array.isArray(segments) ? segments.filter(function(s){ return s && typeof s.text === "string" && s.text.trim(); }) : [];
  if (!blocks.length) blocks = [{ kind: "narration", text: text }];
  var targets = [];
  blocks.forEach(function(segment){
    var spoken = segment.kind === "dialogue";
    var block = document.createElement("div");
    block.className = spoken ? "dialogue-block" : "narration-block";
    var content = document.createElement("div");
    content.className = "speaker-content";
    var label = document.createElement("div");
    label.className = "speaker-name";
    label.textContent = spoken ? (segment.speaker_name || "Unknown voice") : "Narrator";
    if (spoken) block.appendChild(portraitButton(label.textContent, segment.portrait_url));
    content.appendChild(label);
    var body = document.createElement("div");
    body.className = spoken ? "dialogue-text" : "narration-text";
    content.appendChild(body);
    block.appendChild(content);
    row.appendChild(block);
    targets.push({ body: body, block: block, text: segment.text });
  });
  if (animate) revealDialogue(row, targets, getTypewriterDelay());
  else targets.forEach(function(t){ t.body.innerHTML = formatMsgText(t.text); });
}

// A single animation clock preserves reading order across speakers. Elapsed-time
// batching avoids browser timer clamping and thousands of one-letter DOM nodes.
function revealDialogue(row, targets, delay) {
  if (_typewriterAbort) _typewriterAbort.abort();
  var controller = new AbortController();
  _typewriterAbort = controller;
  var frame = 0, elapsed = 0, previous = performance.now(), targetIndex = 0, index = 0;
  targets.forEach(function(t){ t.chars = Array.from(t.text.replace(/\\n/g, "\n")); t.block.hidden = true; });
  row.classList.add("typing-active");
  row.setAttribute("aria-busy", "true");
  var skip = document.createElement("button");
  skip.className = "reveal-skip";
  skip.type = "button";
  skip.textContent = "Show full reply";
  row.appendChild(skip);
  function finish() {
    cancelAnimationFrame(frame);
    targets.forEach(function(t){ t.block.hidden = false; t.body.innerHTML = formatMsgText(t.text); });
    row.classList.remove("typing-active");
    row.removeAttribute("aria-busy");
    skip.remove();
    row.removeEventListener("click", tap);
    if (_typewriterAbort === controller) _typewriterAbort = null;
  }
  function tap(e){ if (!e.target.closest(".speaker-portrait, a")) finish(); }
  controller.signal.addEventListener("abort", finish, { once: true });
  row.addEventListener("click", tap);
  function step(now) {
    var scroller = document.getElementById("chat-messages");
    var follow = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 100;
    elapsed += now - previous;
    previous = now;
    while (targetIndex < targets.length) {
      var t = targets[targetIndex];
      t.block.hidden = false;
      while (index < t.chars.length) {
        var ch = t.chars[index];
        var cost = delay * (/[.!?]/.test(ch) ? 4 : /[,;:]/.test(ch) ? 2 : 1);
        if (elapsed < cost) break;
        elapsed -= cost;
        index++;
      }
      t.body.textContent = t.chars.slice(0, index).join("");
      if (index < t.chars.length) break;
      t.body.innerHTML = formatMsgText(t.text);
      targetIndex++; index = 0;
    }
    if (follow) scrollChatToBottom();
    if (targetIndex >= targets.length) finish();
    else frame = requestAnimationFrame(step);
  }
  frame = requestAnimationFrame(step);
}

return { render: renderDialogueTurn, portraitButton: portraitButton, finish: function(){ if (_typewriterAbort) _typewriterAbort.abort(); } };
};

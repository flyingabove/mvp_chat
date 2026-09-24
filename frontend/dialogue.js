window.createDialoguePresentation = function(helpers) {
var renderAvatarImage = helpers.renderAvatarImage;
var formatMsgText = helpers.formatMsgText;
var scrollChatToBottom = helpers.scrollChatToBottom;
var _typewriterAbort = null;

function speakerInitials(name) {
  return String(name || "?").split(/\s+/).slice(0, 2).map(function(part){
    return Array.from(part)[0] || "";
  }).join("").toUpperCase();
}

function isUsablePortrait(src) {
  return typeof src === "string" && src.indexOf("/img/") === 0 &&
    src.indexOf("..") < 0 && src !== "/img/avatars/persona_default.svg";
}

function portraitButton(name, src, compact) {
  var button = document.createElement("button");
  button.type = "button";
  button.className = compact ? "speaker-portrait msg-avatar" : "speaker-portrait";
  button.title = name;
  button.setAttribute("aria-label", "View picture of " + name);
  if (isUsablePortrait(src)) {
    var img = renderAvatarImage(button, src, name);
    img.addEventListener("error", function(){
      button.textContent = speakerInitials(name);
      button.onclick = function(){ openPortrait(name, null, button); };
    }, { once: true });
  } else {
    button.textContent = speakerInitials(name);
  }
  button.onclick = function(){ openPortrait(name, isUsablePortrait(src) ? src : null, button); };
  return button;
}

function openPortrait(name, src, opener) {
  var dialog = document.getElementById("portrait-viewer");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "portrait-viewer";
    dialog.setAttribute("aria-labelledby", "portrait-viewer-name");
    dialog.innerHTML = '<button type="button" class="portrait-close" aria-label="Close picture">&times;</button><div class="portrait-full"></div><h2 id="portrait-viewer-name"></h2>';
    document.body.appendChild(dialog);
    dialog.querySelector("button").onclick = function(){ dialog.close(); };
    dialog.addEventListener("click", function(event){ if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("close", function(){ if (dialog._opener && dialog._opener.isConnected) dialog._opener.focus(); });
  }
  dialog._opener = opener;
  dialog.querySelector("h2").textContent = name;
  var full = dialog.querySelector(".portrait-full");
  full.textContent = "";
  if (src) {
    var image = renderAvatarImage(full, src, name);
    image.onerror = function(){ full.textContent = speakerInitials(name); };
  } else {
    full.textContent = speakerInitials(name);
  }
  dialog.showModal();
}

// Keep one stable game identity around the scene; each spoken passage owns
// its own portrait and name. Never infer a speaker from unlabelled prose.
function renderDialogueTurn(row, text, segments, animate, fallback) {
  var identity = fallback || { name: "Game", src: null };
  var avatar = portraitButton(identity.name || "Game", identity.src, true);
  var bubble = document.createElement("div");
  bubble.className = "msg-bubble npc";
  row.appendChild(avatar);
  row.appendChild(bubble);
  var parts = Array.isArray(segments) && segments.length ? segments : [{kind: "narration", text: text}];
  var blocks = [];
  parts.forEach(function(segment){
    if (!segment || typeof segment.text !== "string" || !segment.text.trim()) return;
    var container = document.createElement("div");
    var body = document.createElement("div");
    if (segment.kind === "dialogue") {
      container.className = "scene-speech";
      var name = segment.speaker_name || "Unknown speaker";
      container.appendChild(portraitButton(name, segment.portrait_url, false));
      var speech = document.createElement("div");
      speech.className = "speech-bubble";
      var label = document.createElement("div");
      label.className = "speaker-name";
      label.textContent = name;
      speech.appendChild(label);
      speech.appendChild(body);
      container.appendChild(speech);
    } else {
      container.className = "scene-narration";
      container.appendChild(body);
    }
    bubble.appendChild(container);
    blocks.push({container: container, body: body, text: segment.text});
  });
  if (animate) revealBlocks(row, bubble, blocks, helpers.getTypewriterDelay());
  else blocks.forEach(function(block){ block.body.innerHTML = formatMsgText(block.text); });
}

// One animation clock reveals the ordered scene without removing its portraits.
function revealBlocks(row, bubble, blocks, delay) {
  if (_typewriterAbort) _typewriterAbort.abort();
  var controller = new AbortController();
  _typewriterAbort = controller;
  var frame = 0, elapsed = 0, previous = performance.now(), index = 0, blockIndex = 0;
  blocks.forEach(function(block){ block.chars = Array.from(block.text.replace(/\\n/g, "\n")); block.container.hidden = true; });
  row.setAttribute("aria-busy", "true");
  bubble.classList.add("typing-active");
  function finish() {
    cancelAnimationFrame(frame);
    blocks.forEach(function(block){ block.container.hidden = false; block.body.innerHTML = formatMsgText(block.text); });
    bubble.classList.remove("typing-active");
    row.removeAttribute("aria-busy");
    bubble.removeEventListener("click", skip);
    if (_typewriterAbort === controller) _typewriterAbort = null;
    scrollChatToBottom();
  }
  function skip(event){ if (!event.target.closest || !event.target.closest("button")) finish(); }
  controller.signal.addEventListener("abort", finish, { once: true });
  bubble.addEventListener("click", skip);
  function step(now) {
    var scroller = document.getElementById("chat-messages");
    var follow = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 100;
    elapsed += now - previous;
    previous = now;
    while (blockIndex < blocks.length) {
      var block = blocks[blockIndex];
      block.container.hidden = false;
      while (index < block.chars.length) {
        var ch = block.chars[index];
        var cost = delay * (/[.!?]/.test(ch) ? 4 : /[,;:]/.test(ch) ? 2 : 1);
        if (elapsed < cost) break;
        elapsed -= cost;
        index++;
      }
      block.body.textContent = block.chars.slice(0, index).join("");
      if (index < block.chars.length) break;
      block.body.innerHTML = formatMsgText(block.text);
      blockIndex++;
      index = 0;
    }
    if (follow) scrollChatToBottom();
    if (blockIndex >= blocks.length) finish();
    else frame = requestAnimationFrame(step);
  }
  frame = requestAnimationFrame(step);
}

return {
  render: renderDialogueTurn,
  portraitButton: portraitButton,
  finish: function(){ if (_typewriterAbort) _typewriterAbort.abort(); }
};
};

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

/* Pick one identity for the whole reply. Dialogue length is accumulated per
   canonical speaker. Unknown speakers still participate in ranking, but their
   winning result intentionally resolves to the game cover. */
function dominantIdentity(segments, fallback) {
  var game = fallback || { name: "Game", src: null };
  var totals = Object.create(null);
  var order = [];
  (Array.isArray(segments) ? segments : []).forEach(function(segment){
    if (!segment || segment.kind !== "dialogue" || typeof segment.text !== "string") return;
    var rawId = String(segment.speaker_id || "unknown").trim().toLowerCase();
    var id = rawId && rawId !== "null" ? rawId : "unknown";
    if (!totals[id]) {
      totals[id] = { count: 0, id: id, name: segment.speaker_name, src: segment.portrait_url };
      order.push(id);
    }
    totals[id].count += Array.from(segment.text.trim()).length;
  });
  if (!order.length) return game;
  var winner = totals[order[0]];
  order.slice(1).forEach(function(id){ if (totals[id].count > winner.count) winner = totals[id]; });
  if (winner.id === "unknown" || !winner.name || !isUsablePortrait(winner.src)) return game;
  return { name: winner.name, src: winner.src };
}

function renderDialogueTurn(row, text, segments, animate, fallback) {
  var identity = dominantIdentity(segments, fallback);
  var avatar = portraitButton(identity.name || "Game", identity.src, true);
  var bubble = document.createElement("div");
  bubble.className = "msg-bubble npc";
  row.appendChild(avatar);
  row.appendChild(bubble);
  if (animate) revealBubble(row, bubble, text, helpers.getTypewriterDelay());
  else bubble.innerHTML = formatMsgText(text);
}

// One animation clock updates a text node once per frame and preserves the
// existing 3x-faster preference values without creating one DOM node per letter.
function revealBubble(row, bubble, text, delay) {
  if (_typewriterAbort) _typewriterAbort.abort();
  var controller = new AbortController();
  _typewriterAbort = controller;
  var chars = Array.from(String(text || "").replace(/\\n/g, "\n"));
  var frame = 0, elapsed = 0, previous = performance.now(), index = 0;
  row.setAttribute("aria-busy", "true");
  bubble.classList.add("typing-active");
  bubble.textContent = "";
  function finish() {
    cancelAnimationFrame(frame);
    bubble.innerHTML = formatMsgText(text);
    bubble.classList.remove("typing-active");
    row.removeAttribute("aria-busy");
    bubble.removeEventListener("click", finish);
    if (_typewriterAbort === controller) _typewriterAbort = null;
    scrollChatToBottom();
  }
  controller.signal.addEventListener("abort", finish, { once: true });
  bubble.addEventListener("click", finish);
  function step(now) {
    var scroller = document.getElementById("chat-messages");
    var follow = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 100;
    elapsed += now - previous;
    previous = now;
    while (index < chars.length) {
      var ch = chars[index];
      var cost = delay * (/[.!?]/.test(ch) ? 4 : /[,;:]/.test(ch) ? 2 : 1);
      if (elapsed < cost) break;
      elapsed -= cost;
      index++;
    }
    bubble.textContent = chars.slice(0, index).join("");
    if (follow) scrollChatToBottom();
    if (index >= chars.length) finish();
    else frame = requestAnimationFrame(step);
  }
  frame = requestAnimationFrame(step);
}

return {
  render: renderDialogueTurn,
  portraitButton: portraitButton,
  dominantIdentity: dominantIdentity,
  finish: function(){ if (_typewriterAbort) _typewriterAbort.abort(); }
};
};

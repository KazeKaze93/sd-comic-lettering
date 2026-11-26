// ComfyUI side of Comic Lettering: an "Open editor" button on the node. The editor is the
// same page the A1111 family shows (ui/), in a window over ComfyUI. In ComfyUI the node is
// the memory: the page reads the node's widgets on opening and writes every change back, so
// the next run of the workflow gives the picture the editor showed.
import { app } from "../../scripts/app.js";

const NODE_TYPE = "ComicLettering";
const PAGE = "/comic_lettering/ui";
const LAYOUT = "layout";
const BUTTON = "Open editor";
// The three texts: the page's name -> the widget's name.
const TEXTS = { text: "bubbles", caption: "caption", sfx: "sfx" };
// Options the page and the node name differently: the page's name -> the widget's name.
const RENAMED = { spill: "spill_to_caption", erase: "erase_ai_text" };
const PAGE_NAME = Object.fromEntries(Object.entries(RENAMED).map(([page, widget]) => [widget, page]));
// Widgets that are not options of the look.
const NOT_LOOK = new Set([...Object.values(TEXTS), LAYOUT, BUTTON, "show_numbers"]);

let overlay = null;
let frame = null;
let ready = false;
let current = null; // the node the editor is open for

function widget(node, name) {
    return (node.widgets || []).find((entry) => entry.name === name);
}

function readLayout(node) {
    try {
        const data = JSON.parse(widget(node, LAYOUT)?.value || "{}");
        return {
            pins: data && typeof data.pins === "object" && data.pins ? data.pins : {},
            regions: data && Array.isArray(data.regions) ? data.regions : [],
        };
    } catch {
        return { pins: {}, regions: [] };
    }
}

/** What the node holds, in the page's terms. */
function stateOf(node) {
    const settings = {};
    for (const entry of node.widgets || []) {
        if (NOT_LOOK.has(entry.name) || entry.type === "button") continue;
        settings[PAGE_NAME[entry.name] || entry.name] = entry.value;
    }
    const texts = {};
    for (const [page, name] of Object.entries(TEXTS)) texts[page] = String(widget(node, name)?.value ?? "");
    return { texts, settings, layout: readLayout(node) };
}

function setWidget(node, name, value) {
    const entry = widget(node, name);
    if (!entry || entry.value === value) return;
    // A list takes only what it offers; a number widget takes numbers.
    const choices = entry.options?.values;
    if (Array.isArray(choices) && !choices.includes(value)) return;
    if (typeof entry.value === "number" && typeof value !== "number") return;
    entry.value = value;
    entry.callback?.(value);
}

/** Write what the page holds back into the node. */
function applyState(node, state) {
    if (!node || !state) return;
    for (const [page, name] of Object.entries(TEXTS)) {
        if (typeof state.texts?.[page] === "string") setWidget(node, name, state.texts[page]);
    }
    for (const [key, value] of Object.entries(state.settings || {})) setWidget(node, RENAMED[key] || key, value);
    const pins = state.layout?.pins || {};
    const regions = state.layout?.regions || [];
    const empty = !Object.keys(pins).length && !regions.length;
    setWidget(node, LAYOUT, empty ? "" : JSON.stringify({ pins, regions }));
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function send() {
    if (!frame?.contentWindow || !ready || !current) return;
    frame.contentWindow.postMessage(
        {
            type: "SDCL_INIT",
            // The image is the one the node last worked on; the server keeps it under the node's id.
            image: { tab: `node:${current.id}`, url: null, index: 0, count: 1 },
            theme: "dark",
            node: stateOf(current),
        },
        window.location.origin,
    );
}

function close() {
    if (overlay) overlay.style.display = "none";
    current = null;
}

function build() {
    overlay = document.createElement("div");
    overlay.id = "comic-lettering-overlay";
    overlay.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.6);display:none;";
    frame = document.createElement("iframe");
    frame.title = "Comic Lettering";
    frame.src = `${PAGE}?t=${Date.now()}`;
    frame.style.cssText =
        "position:absolute;inset:12px;width:calc(100% - 24px);height:calc(100% - 24px);" +
        "border:1px solid rgba(128,128,128,0.4);border-radius:8px;background:#111317;";
    overlay.appendChild(frame);
    document.body.appendChild(overlay);

    window.addEventListener("message", (event) => {
        if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return;
        const data = event.data || {};
        if (data.type === "SDCL_READY") {
            ready = true;
            send();
        } else if (data.type === "SDCL_CLOSE") {
            close();
        } else if (data.type === "SDCL_STATE") {
            applyState(current, data.state);
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && overlay.style.display !== "none") close();
    });
}

function open(node) {
    if (!overlay) build();
    current = node;
    overlay.style.display = "block";
    send(); // the page itself asks again with SDCL_READY once it has loaded
}

/** The layout widget holds JSON written by the editor: it is kept and saved, but not shown. */
function hide(entry) {
    if (!entry) return;
    entry.hidden = true;
    entry.computeSize = () => [0, -4];
    if (entry.options) entry.options.hidden = true;
}

app.registerExtension({
    name: "sd-comic-lettering.editor",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            hide(widget(this, LAYOUT));
            if (!widget(this, BUTTON)) {
                const button = this.addWidget("button", BUTTON, null, () => open(this));
                // A button holds nothing to save or to send with the prompt.
                button.serialize = false;
                button.options = { ...(button.options || {}), serialize: false };
            }
            return result;
        };
    },
});

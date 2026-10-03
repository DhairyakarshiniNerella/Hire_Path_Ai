import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INDEX_HTML_PATH = path.join(__dirname, "..", "index.html");
const SCRIPT_JS_PATH = path.join(__dirname, "..", "script.js");

/**
 * Loads the real index.html markup into the current jsdom document and
 * evaluates the real script.js in the global scope (indirect eval, so its
 * top-level `function` declarations attach to globalThis exactly like a
 * classic <script> tag would in a browser) - without modifying either file.
 */
export function loadApp() {
  const html = fs.readFileSync(INDEX_HTML_PATH, "utf-8");
  const bodyMatch = html.match(/<body>([\s\S]*)<\/body>/);
  const bodyContent = bodyMatch[1].replace(/<script src="script\.js"><\/script>/, "");
  document.body.innerHTML = bodyContent;

  // jsdom doesn't implement scrollIntoView - script.js calls it as a UX nicety,
  // not something under test, so a no-op polyfill is enough.
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }

  const scriptSource = fs.readFileSync(SCRIPT_JS_PATH, "utf-8");
  const indirectEval = eval;
  indirectEval(scriptSource);
}

import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
import test from "node:test"
import React, {act} from "react"
import {createRoot} from "react-dom/client"
import {JSDOM} from "jsdom"
import {transformWithEsbuild} from "vite"

const source = (await readFile(new URL("../src/Forms.jsx", import.meta.url), "utf8"))
  .replace('from "react"', `from "${import.meta.resolve("react")}"`)
  .replace('from "./api"', `from "${new URL("../src/api.js", import.meta.url).href}"`)
const {code} = await transformWithEsbuild(source, "Forms.jsx", {loader: "jsx"})
const {Editor} = await import("data:text/javascript;base64," + Buffer.from(code).toString("base64"))

const cases = [
  ["10:15:30", "11:45:20"],
  ["10:15:30.123", "11:45:20.456"],
  ["10:15:30.123456", "11:45:20.654321"],
  [null, null],
  ["10:15:30", "11:45:20", {starts_at: "10:30:45", ends_at: "12:00:30"}],
  ["10:15:30", "11:45:20", {starts_at: "", ends_at: ""}],
]

for (const [starts, ends, changes = {}] of cases) {
  test(`activity editor preserves or changes times: ${starts}–${ends} ${JSON.stringify(changes)}`, async () => {
    const dom = new JSDOM('<div id="root"></div>', {url: "http://localhost"})
    const originals = new Map()
    const globals = {
      window: dom.window, document: dom.window.document,
      FormData: dom.window.FormData, IS_REACT_ACT_ENVIRONMENT: true,
    }
    let request, saved = false
    globals.fetch = async (url, options) => {
      request = {url, ...options}
      return {ok: true, status: 200, json: async () => ({id: 7})}
    }
    for (const [key, value] of Object.entries(globals)) {
      originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
      Object.defineProperty(globalThis, key, {value, writable: true, configurable: true})
    }
    dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true }
    dom.window.HTMLDialogElement.prototype.close = function () { this.open = false }
    const root = createRoot(document.getElementById("root"))
    try {
      await act(async () => root.render(React.createElement(Editor, {
        form: {kind: "activities", row: {id: 7, title: "Excursion", activity_date: "2026-06-13", starts_at: starts, ends_at: ends, description: ""}},
        trip: {id: 2, start_date: "2026-06-12", end_date: "2026-06-14"},
        close() {}, saved() { saved = true },
      })))
      document.querySelector('[name="title"]').value = "New title"
      for (const [name, value] of Object.entries(changes)) document.querySelector(`[name="${name}"]`).value = value
      const form = document.querySelector("form")
      assert.equal(form.checkValidity(), true, "the browser must allow submitting the original times")
      await act(async () => form.dispatchEvent(new dom.window.Event("submit", {bubbles: true, cancelable: true})))
      assert.equal(request.url, "/api/trips/2/activities/7")
      assert.equal(request.method, "PUT")
      const body = JSON.parse(request.body)
      assert.equal(body.title, "New title")
      assert.equal(body.starts_at, "starts_at" in changes ? changes.starts_at || null : starts)
      assert.equal(body.ends_at, "ends_at" in changes ? changes.ends_at || null : ends)
      assert.equal(saved, true)
    } finally {
      await act(async () => root.unmount())
      dom.window.close()
      for (const [key, descriptor] of originals) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor)
        else delete globalThis[key]
      }
    }
  })
}

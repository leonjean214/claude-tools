import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import ledger from "./index.ts";

test("assistant message_end appends the contract, including no-session", () => {
	const dir = mkdtempSync(join(tmpdir(), "pi-ledger-"));
	const previous = { ...process.env };
	try {
		process.env.PI_USAGE_LEDGER_DIR = dir;
		process.env.PI_USAGE_ROLE = "reviewer";
		process.env.PI_USAGE_PARENT = "parent-123";
		let handler;
		ledger({ on(event, callback) { assert.equal(event, "message_end"); handler = callback; } });
		const now = new Date();
		const message = { role: "assistant", timestamp: now.getTime(), provider: "openai-codex",
			model: "gpt-6.1-sol", responseId: "resp-1",
			usage: { input: 10, output: 2, cacheRead: 3, cacheWrite: 4, totalTokens: 19, cost: { total: 0.25 } } };
		const ctx = { cwd: "/work", sessionManager: { getSessionFile: () => undefined } };
		handler({ message: { role: "user" } }, ctx);
		handler({ message }, ctx);
		const filename = join(dir, `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}.jsonl`);
		let lines = readFileSync(filename, "utf8").trim().split("\n");
		assert.equal(lines.length, 1);
		assert.ok(Buffer.byteLength(lines[0] + "\n") < 4096);
		assert.deepEqual(JSON.parse(lines[0]), {
			ts: now.toISOString(), pid: process.pid, ppid: process.ppid,
			provider: "openai-codex", model: "gpt-6.1-sol", responseId: "resp-1",
			usage: { input: 10, output: 2, cacheRead: 3, cacheWrite: 4, totalTokens: 19, costTotal: 0.25 },
			session: null, cwd: "/work", role: "reviewer", parent: "parent-123",
		});
		delete process.env.PI_USAGE_ROLE;
		delete process.env.PI_USAGE_PARENT;
		delete message.responseId;
		delete message.usage.cost;
		ctx.sessionManager.getSessionFile = () => "/session.jsonl";
		handler({ message }, ctx);
		lines = readFileSync(filename, "utf8").trim().split("\n");
		const row = JSON.parse(lines[1]);
		assert.equal(row.session, "/session.jsonl");
		assert.equal(row.responseId, null);
		assert.equal(row.usage.costTotal, null);
		assert.equal(row.role, null);
		assert.equal(row.parent, null);
		// A file as the directory gives a deterministic failure even as root/on Windows.
		const blocked = join(dir, "not-a-directory");
		writeFileSync(blocked, "blocked");
		process.env.PI_USAGE_LEDGER_DIR = blocked;
		assert.doesNotThrow(() => handler({ message }, ctx));
	} finally {
		process.env = previous;
		rmSync(dir, { recursive: true, force: true });
	}
});

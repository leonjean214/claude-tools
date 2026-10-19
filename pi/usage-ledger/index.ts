import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function usageLedger(pi: ExtensionAPI): void {
	pi.on("message_end", (event, ctx) => {
		if (event.message.role !== "assistant") return;
		try {
			const message = event.message;
			const usage = message.usage;
			const now = new Date();
			const dir = process.env.PI_USAGE_LEDGER_DIR ?? join(homedir(), ".pi", "agent", "usage-ledger");
			const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
			const row = {
				ts: new Date(message.timestamp).toISOString(),
				pid: process.pid,
				ppid: process.ppid,
				provider: message.provider,
				model: message.model,
				responseId: message.responseId ?? null,
				usage: {
					input: usage.input,
					output: usage.output,
					cacheRead: usage.cacheRead,
					cacheWrite: usage.cacheWrite,
					totalTokens: usage.totalTokens,
					costTotal: usage.cost?.total ?? null,
				},
				session: ctx.sessionManager.getSessionFile() ?? null,
				cwd: ctx.cwd,
				role: process.env.PI_USAGE_ROLE ?? null,
				parent: process.env.PI_USAGE_PARENT ?? null,
			};
			const line = JSON.stringify(row) + "\n";
			if (Buffer.byteLength(line, "utf8") >= 4096) return;
			mkdirSync(dir, { recursive: true });
			appendFileSync(join(dir, `${month}.jsonl`), line, "utf8");
		} catch {
			// Accounting must never interrupt a pi run (including --no-session).
		}
	});
}

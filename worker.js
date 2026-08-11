// worker.js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // internal auth: header x-api-key должен совпадать с WORKER_API_KEY в секретах Cloudflare
    const apiKey = request.headers.get('x-api-key');
    if (!apiKey || apiKey !== env.WORKER_API_KEY) {
      return new Response('Unauthorized', { status: 401 });
    }

    if (path === "/store_session" && method === "POST") {
      const { session } = await request.json();
      await env.DB.prepare("INSERT OR REPLACE INTO sessions (id, token) VALUES (?, ?)").bind(1, session).run();
      return new Response(JSON.stringify({ ok: true }));
    }

    if (path === "/get_session" && method === "GET") {
      const res = await env.DB.prepare("SELECT token FROM sessions WHERE id = ?").bind(1).first();
      if (!res) return new Response(JSON.stringify({ session: null }));
      return new Response(JSON.stringify({ session: res.token }));
    }

    if (path === "/delete_session" && method === "POST") {
      await env.DB.prepare("DELETE FROM sessions WHERE id = ?").bind(1).run();
      return new Response(JSON.stringify({ ok: true }));
    }

    if (path === "/add_group" && method === "POST") {
      const { link } = await request.json();
      await env.DB.prepare("INSERT OR IGNORE INTO groups (link) VALUES (?)").bind(link).run();
      return new Response(JSON.stringify({ ok: true }));
    }

    if (path === "/groups" && method === "GET") {
      const res = await env.DB.prepare("SELECT id, link FROM groups").all();
      return new Response(JSON.stringify(res.results));
    }

    if (path === "/run_parser" && method === "POST") {
      await env.DB.prepare("INSERT INTO tasks (type, status) VALUES (?, ?)").bind("parse", "pending").run();
      return new Response(JSON.stringify({ ok: true, msg: "parse scheduled" }));
    }

    if (path === "/run_add" && method === "POST") {
      await env.DB.prepare("INSERT INTO tasks (type, status) VALUES (?, ?)").bind("add", "pending").run();
      return new Response(JSON.stringify({ ok: true, msg: "add scheduled" }));
    }

    if (path === "/stats" && method === "GET") {
      const res = await env.DB.prepare("SELECT * FROM stats").all();
      return new Response(JSON.stringify(res.results));
    }

    return new Response("Not found", { status: 404 });
  }
}

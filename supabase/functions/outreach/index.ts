// Outreach list for signed-in partners. Requires a Supabase Auth session whose email
// is on app.outreach_users. Every request is recorded in app.access_log.
// action "map" returns parcel shapes with each listed parcel's status (site_outreach_map).
import { createClient } from "npm:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const url = Deno.env.get("SUPABASE_URL")!;
const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ status: "error" }, 405);
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: u, error: uerr } = await admin.auth.getUser(token);
  if (uerr || !u?.user?.email) return json({ status: "signed_out" }, 401);
  let action = "view";
  try {
    const body = await req.json();
    if (["check", "view", "export", "map"].includes(body?.action)) action = body.action;
  } catch { /* default view */ }
  const { data, error } = action === "map"
    ? await admin.rpc("site_outreach_map", { p_email: u.user.email })
    : await admin.rpc("site_outreach", { p_email: u.user.email, p_action: action });
  if (error) {
    console.error(error);
    return json({ status: "error" }, 500);
  }
  if (data?.status === "not_allowed") return json(data, 403);
  return json(data);
});

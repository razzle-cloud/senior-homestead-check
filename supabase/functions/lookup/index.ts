// Public address lookup for the Decatur homestead website.
// No sign-in: protected by input checks and per-visitor rate limits in public.site_lookup.
import { createClient } from "npm:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
  auth: { persistSession: false },
});

async function hashIp(ip: string) {
  // daily-rotating salt so stored hashes cannot be reversed or linked across days
  const day = new Date().toISOString().slice(0, 10);
  const data = new TextEncoder().encode(`${day}|decatur-homestead|${ip}`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ status: "error", message: "Use POST" }, 405);
  let q = "";
  try {
    const body = await req.json();
    q = String(body?.q ?? "").slice(0, 120);
  } catch {
    return json({ status: "error", message: "Bad request" }, 400);
  }
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "unknown";
  const { data, error } = await admin.rpc("site_lookup", { q, ip_hash: await hashIp(ip) });
  if (error) {
    console.error(error);
    return json({ status: "error", message: "Lookup failed" }, 500);
  }
  return json(data);
});

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Ohne Supabase-Konfiguration läuft die App im Entwicklungsmodus mit dem Demo-Schlüssel.
export const supabase: SupabaseClient | null =
  URL && ANON ? createClient(URL, ANON, { auth: { persistSession: true, detectSessionInUrl: true } }) : null;

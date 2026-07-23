import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";

/**
 * Supabase auth session.
 * - undefined: still loading
 * - null: signed out (or Supabase not configured)
 * - object: active session (session.access_token is sent as Bearer by api.js)
 */
export function useSession() {
  const [session, setSession] = useState(undefined);

  useEffect(() => {
    if (!supabase) {
      setSession(null);
      return undefined;
    }
    supabase.auth.getSession().then(({ data }) => setSession(data.session ?? null));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next ?? null);
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  return session;
}

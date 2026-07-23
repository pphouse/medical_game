import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "../api";

const ProfileContext = createContext(null);

/** Loads (and auto-bootstraps) the API-side Profile for the signed-in user. */
export function ProfileProvider({ children }) {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    const me = await api.me();
    setProfile(me);
    return me;
  }, []);

  useEffect(() => {
    api
      .bootstrap()
      .then(setProfile)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <ProfileContext.Provider value={{ profile, refresh, error }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  const value = useContext(ProfileContext);
  if (!value) throw new Error("useProfile must be used inside <ProfileProvider>");
  return value;
}

import type { User } from "../types";

let _user: User | null = null;
let _token: string | null = localStorage.getItem("access_token");

try {
  const stored = localStorage.getItem("user");
  if (stored) _user = JSON.parse(stored);
} catch {}

export const getStoredAuth = () => ({ user: _user, token: _token });

export const storeAuth = (token: string, user: User) => {
  localStorage.setItem("access_token", token);
  localStorage.setItem("user", JSON.stringify(user));
  _user = user;
  _token = token;
};

export const clearAuth = () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user");
  _user = null;
  _token = null;
};

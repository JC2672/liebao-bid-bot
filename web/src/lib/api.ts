import axios from "axios";

export const api = axios.create({ baseURL: "http://localhost:8000" });

export interface GateResult {
  source: string;
  external_id: string;
  url: string;
  company: string;
  title: string;
  location: string;
  description: string;
  posted_at: string | null;
  passed: boolean;
  reject_reason: string | null;
  flags: string[];
}

export interface FetchCounts {
  fetched: number;
  deduped: number;
  passed: number;
  rejected: number;
}

export interface Profile {
  id: string;
  name: string;
  title: string;
  location: string;
  phone: string;
  email: string;
  linkedin: string;
  sheet_id: string;
  sheet_tab: string;
  output_root: string;
  template: string;
}

export interface ProfileDetail extends Profile {
  prompt: string;
}

export interface ProfileInput {
  id?: string;
  name: string;
  title: string;
  location: string;
  phone: string;
  email: string;
  linkedin: string;
  sheet_id: string;
  sheet_tab: string;
  output_root: string;
  prompt: string;
}

export type OpportunityStatus = "queued" | "generating" | "ready" | "failed";

export interface Opportunity {
  id: number;
  profile: string;
  company: string;
  title: string;
  location: string;
  source: string;
  url: string;
  description: string;
  status: OpportunityStatus;
  error: string | null;
  resume_json: string | null;
  staging_dir: string | null;
  created_at: string;
  updated_at: string;
}

export const SOURCE_OPTIONS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "indeed", label: "Indeed" },
  { id: "zip_recruiter", label: "ZipRecruiter" },
  { id: "glassdoor", label: "Glassdoor" },
  { id: "google", label: "Google Jobs" },
  { id: "dice", label: "Dice" },
];

export async function runFetch(sources: string[], query: string, postedWithinDays: number) {
  const { data } = await api.post<{ results: GateResult[]; counts: FetchCounts }>("/fetch", {
    sources,
    query,
    posted_within_days: postedWithinDays,
  });
  return data;
}

export async function exportShortlist(rows: GateResult[]) {
  const response = await api.post("/fetch/export", rows, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  const disposition = response.headers["content-disposition"] as string | undefined;
  const match = disposition?.match(/filename="(.+)"/);
  link.href = url;
  link.download = match?.[1] ?? "shortlist.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function listProfiles() {
  const { data } = await api.get<Profile[]>("/profiles");
  return data;
}

export async function getProfile(id: string) {
  const { data } = await api.get<ProfileDetail>(`/profiles/${id}`);
  return data;
}

export async function createProfile(input: ProfileInput) {
  const { data } = await api.post<Profile>("/profiles", input);
  return data;
}

export async function updateProfile(id: string, input: ProfileInput) {
  const { data } = await api.put<Profile>(`/profiles/${id}`, input);
  return data;
}

export async function deleteProfile(id: string) {
  await api.delete(`/profiles/${id}`);
}

export async function listQueue(profile: string) {
  const { data } = await api.get<Opportunity[]>("/queue", { params: { profile } });
  return data;
}

export async function importShortlist(profile: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<{ inserted: number; skipped: number }>(
    "/queue/import",
    form,
    { params: { profile }, headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

export async function markApplied(id: number) {
  const { data } = await api.post<{ folder: string }>(`/queue/${id}/applied`);
  return data;
}

export async function removeOpportunity(id: number) {
  await api.post(`/queue/${id}/remove`);
}

export async function retryOpportunity(id: number) {
  await api.post(`/queue/${id}/retry`);
}

export async function openFolder(id: number) {
  await api.post(`/queue/${id}/open-folder`);
}

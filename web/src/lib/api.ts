import axios from "axios";

// 127.0.0.1, not "localhost" - some VPN clients override DNS so "localhost"
// no longer resolves to loopback. See start.bat and main.py's CORS config.
export const api = axios.create({ baseURL: "http://127.0.0.1:8000" });

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
  location: string;
  phone: string;
  email: string;
  linkedin: string;
  sheet_id: string;
  sheet_tab: string;
  output_root: string;
  template_id: string;
}

export interface ProfileDetail extends Profile {
  prompt: string;
}

export interface ProfileInput {
  name: string;
  location: string;
  phone: string;
  email: string;
  linkedin: string;
  sheet_id: string;
  sheet_tab: string;
  output_root: string;
  template_id: string;
  prompt: string;
}

// Templates are independent of Profiles - a profile just references one by
// id (Profile.template_id), a live reference not a copy: editing a template
// changes what every profile using it renders next. See templates.py.
export interface Template {
  id: string;
  name: string;
}

export interface TemplateDetail extends Template {
  html: string;
}

export interface TemplateInput {
  name: string;
  html: string;
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
  { id: "linkedin", label: "LinkedIn", domain: "linkedin.com" },
  { id: "indeed", label: "Indeed", domain: "indeed.com" },
  { id: "dice", label: "Dice", domain: "dice.com" },
  { id: "remotive", label: "Remotive", domain: "remotive.com" },
  { id: "remoteok", label: "RemoteOK", domain: "remoteok.com" },
  { id: "weworkremotely", label: "We Work Remotely", domain: "weworkremotely.com" },
  { id: "jobgether", label: "Jobgether", domain: "jobgether.com" },
  { id: "jobright", label: "Jobright", domain: "jobright.ai" },
  { id: "himalayas", label: "Himalayas", domain: "himalayas.app" },
  { id: "jobicy", label: "Jobicy", domain: "jobicy.com" },
  { id: "arbeitnow", label: "Arbeitnow", domain: "arbeitnow.com" },
  { id: "workingnomads", label: "Working Nomads", domain: "workingnomads.com" },
  { id: "greenhouse", label: "Greenhouse", domain: "greenhouse.io" },
  { id: "lever", label: "Lever", domain: "lever.co" },
  { id: "ashby", label: "Ashby", domain: "ashbyhq.com" },
  { id: "talent", label: "Talent.com", domain: "talent.com" },
  { id: "builtin", label: "Built In", domain: "builtin.com" },
  { id: "jobspresso", label: "Jobspresso", domain: "jobspresso.co" },
  { id: "monster", label: "Monster", domain: "monster.com" },
];

// Google's favicon service, keyed by domain - gets every source's real logo
// without needing a brand-icon library that wouldn't cover the smaller job
// boards (Dice, Jobgether, Jobright, RemoteOK, Remotive, We Work Remotely
// aren't in most icon packs; this covers all eleven uniformly).
export function sourceIconUrl(domain: string) {
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;
}

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

export async function listTemplates() {
  const { data } = await api.get<Template[]>("/templates");
  return data;
}

export async function getTemplate(id: string) {
  const { data } = await api.get<TemplateDetail>(`/templates/${id}`);
  return data;
}

export async function createTemplate(input: TemplateInput) {
  const { data } = await api.post<Template>("/templates", input);
  return data;
}

export async function updateTemplate(id: string, input: TemplateInput) {
  const { data } = await api.put<Template>(`/templates/${id}`, input);
  return data;
}

export async function deleteTemplate(id: string) {
  await api.delete(`/templates/${id}`);
}

export function templatePreviewUrl(id: string, format: "html" | "pdf") {
  return `${api.defaults.baseURL}/templates/${id}/preview.${format}`;
}

export async function pickFolder(description: string) {
  const { data } = await api.post<{ path: string | null }>("/pick-folder", null, {
    params: { description },
  });
  return data.path;
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

export async function bulkRemove(ids: number[]) {
  await api.post("/queue/bulk-remove", { ids });
}

export async function bulkRetry(ids: number[]) {
  await api.post("/queue/bulk-retry", { ids });
}

export async function openFolder(id: number) {
  await api.post(`/queue/${id}/open-folder`);
}


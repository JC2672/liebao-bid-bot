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
  sheet_webapp_url: string;
  sheet_secret: string;
  sheet_tab: string;
  output_root: string;
  template_id: string;
  field_id: string;
  country: string;
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
  sheet_webapp_url: string;
  sheet_secret: string;
  sheet_tab: string;
  output_root: string;
  template_id: string;
  field_id: string;
  country: string;
  prompt: string;
}

// Tech fields (Salesforce, Data Engineering, ...) - what Profile.field_id
// points at. Generalizes what used to be hardcoded Salesforce-only query/
// relevance logic; see backend/app/fields.py and gates.py.
export interface FieldConfig {
  id: string;
  name: string;
  query_term: string;
  title_list: string[];
  relevance_allow: string[];
  relevance_deny: string[];
}

export interface FieldInput {
  name: string;
  query_term: string;
  title_list: string[];
  relevance_allow: string[];
  relevance_deny: string[];
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

export interface SourceProgress {
  name: string;
  status: "pending" | "running" | "done" | "failed";
  count: number | null;
}

export interface FetchStatus {
  running: boolean;
  sources: SourceProgress[];
  result: { results: GateResult[]; counts: FetchCounts } | null;
  error: string | null;
}

export async function startFetch(sources: string[], profileId: string, postedWithinDays: number) {
  const { data } = await api.post<{ started: boolean }>("/fetch/start", {
    sources,
    profile: profileId,
    posted_within_days: postedWithinDays,
  });
  return data;
}

export async function getFetchStatus() {
  const { data } = await api.get<FetchStatus>("/fetch/status");
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

// Same dedupe /queue/import does (Sheet applied + current queue), but
// skips the export-to-XLSX-then-upload roundtrip - takes a Fetch run's
// shortlist rows directly. Powers Fetch's "Auto-queue & generate" checkbox.
// Returns the newly-inserted rows' ids, not just a count, so the caller
// can bulk-generate exactly those rows next.
export async function importFetchResults(profile: string, rows: GateResult[]) {
  const { data } = await api.post<{ inserted: number; skipped: number; ids: number[] }>(
    "/queue/import-direct",
    {
      profile,
      rows: rows.map((r) => ({
        company: r.company,
        title: r.title,
        location: r.location,
        source: r.source,
        url: r.url,
        description: r.description,
      })),
    },
  );
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

// Remaining/ETA for whatever's currently generating - see generation.py's
// get_progress() for how it's tracked (in-memory, not persisted - the
// opportunities table's updated_at gets overwritten on every status
// change, so there's nothing in the DB to compute a job's actual duration
// from). `profile` omitted: resolves to whichever profile the current run
// actually belongs to - the floating status widget isn't scoped to any
// one tab, so it has no profile of its own to ask about.
export interface QueueProgress {
  active: boolean;
  profile: string | null;
  completed: number;
  total: number;
  remaining: number;
  ready: number;
  failed: number;
  cancelled: number;
  avg_seconds_per_job: number | null;
  eta_seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
  total_elapsed_seconds: number | null;
}

export async function getQueueProgress(profile?: string) {
  const { data } = await api.get<QueueProgress>("/queue/progress", { params: profile ? { profile } : {} });
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

export async function generateOpportunity(id: number) {
  await api.post(`/queue/${id}/generate`);
}

export async function bulkRemove(ids: number[]) {
  await api.post("/queue/bulk-remove", { ids });
}

export async function bulkRetry(ids: number[]) {
  await api.post("/queue/bulk-retry", { ids });
}

export async function bulkGenerate(ids: number[]) {
  await api.post("/queue/bulk-generate", { ids });
}

export async function openFolder(id: number) {
  await api.post(`/queue/${id}/open-folder`);
}

export async function listFields() {
  const { data } = await api.get<FieldConfig[]>("/fields");
  return data;
}

export async function getField(id: string) {
  const { data } = await api.get<FieldConfig>(`/fields/${id}`);
  return data;
}

export async function createField(input: FieldInput) {
  const { data } = await api.post<FieldConfig>("/fields", input);
  return data;
}

export async function updateField(id: string, input: FieldInput) {
  const { data } = await api.put<FieldConfig>(`/fields/${id}`, input);
  return data;
}

export async function deleteField(id: string) {
  await api.delete(`/fields/${id}`);
}

export async function checkJobrightStatus(): Promise<{ logged_in: boolean }> {
  const { data } = await api.get("/sources/jobright/status");
  return data;
}

export async function triggerJobrightLogin(): Promise<{ started: boolean }> {
  const { data } = await api.post("/sources/jobright/login");
  return data;
}


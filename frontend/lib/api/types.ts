export type User = {
  id: string;
  email: string;
  full_name: string;
  company_name: string | null;
  physical_address: string | null;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
};

export type SMTPAccount = {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  from_email: string;
  from_name: string | null;
  use_tls: boolean;
  use_ssl: boolean;
  hourly_limit: number;
  daily_limit: number;
  is_active: boolean;
  health_status: string;
  consecutive_failures: number;
  last_tested_at: string | null;
  last_error: string | null;
  created_at: string;
};

export type Template = {
  id: string;
  name: string;
  subject: string;
  html_body: string;
  text_body: string;
  ai_instructions: string | null;
  variables: string[];
  created_at: string;
  updated_at: string;
};

export type TemplateAsset = {
  id: string;
  template_id: string | null;
  original_filename: string;
  content_type: string;
  kind: string;
  size_bytes: number;
  checksum_sha256: string;
  placeholder_key: string;
  preview_url: string;
  inline_placeholder: string;
  link_placeholder: string;
  access_count: number;
  download_count: number;
  created_at: string;
  updated_at: string;
};

export type LeadGroup = {
  id: string;
  name: string;
  lead_count: number;
  match_count?: number;
  purpose?: string;
  created_at: string;
  leads?: Lead[];
};

export type LeadFacets = {
  countries: string[];
  study_opportunities: string[];
};

export type Lead = {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  company: string | null;
  title: string | null;
  industry: string | null;
  website: string | null;
  country?: string | null;
  study_opportunity?: string | null;
  role_verified?: boolean;
  email_kind?: string;
  custom_fields: Record<string, string>;
  is_valid: boolean;
  created_at: string;
};

export type Campaign = {
  id: string;
  name: string;
  template_id: string | null;
  status: string;
  ai_enabled: boolean;
  ai_instructions: string | null;
  hourly_limit: number;
  daily_limit: number;
  delay_seconds: number;
  total_count: number;
  queued_count: number;
  sent_count: number;
  failed_count: number;
  bounced_count: number;
  open_count: number;
  click_count: number;
  unsubscribe_count: number;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type Dashboard = {
  active_campaigns: number;
  total_leads: number;
  emails_sent: number;
  tracked_opens: number;
  clicks: number;
  failures: number;
  bounce_signals: number;
  recent_campaigns: Campaign[];
};

export type ImportResult = {
  id: string;
  filename: string;
  status: string;
  total_rows: number;
  valid_count: number;
  invalid_count: number;
  duplicate_count: number;
  column_mapping: Record<string, string>;
  error_report: Array<Record<string, string | number>>;
  group_id?: string | null;
  group_name?: string | null;
};

export type CampaignPreview = {
  lead_id: string;
  email: string;
  subject: string;
  html_body: string;
  text_body: string;
  personalization: Record<string, string>;
};

export type OpenClassification =
  | "none"
  | "likely_automated"
  | "proxy_or_uncertain"
  | "possible_human"
  | "open_signal";

export type TrackingRequest = {
  id: string;
  request_type: string;
  classification: string;
  confidence: number;
  classification_reasons: string[];
  seconds_after_send: number | null;
  user_agent: string | null;
  created_at: string;
  asset_id: string | null;
  filename: string | null;
};

export type AssetActivity = {
  asset_id: string;
  filename: string;
  kind: string;
  access_count: number;
  download_count: number;
  image_loads: number;
  pdf_accesses: number;
  downloads: number;
};

export type CampaignEmail = {
  id: string;
  campaign_id: string;
  lead_id: string;
  recipient_email: string;
  status: string;
  subject: string;
  error_message: string | null;
  sent_at: string | null;
  created_at: string;
  opened: boolean;
  opened_at: string | null;
  latest_open_at: string | null;
  open_classification: OpenClassification;
  open_request_count: number;
  open_confidence: number | null;
  open_reasons: string[];
  clicked: boolean;
  click_count: number;
  links: Array<{
    destination_url: string;
    click_count: number;
    clicked: boolean;
    asset_id?: string | null;
  }>;
  assets: AssetActivity[];
  requests: TrackingRequest[];
};

export type CampaignAnalytics = {
  sent: number;
  queued: number;
  failed: number;
  bounced: number;
  tracked_opens: number;
  open_requests: number;
  automated_opens: number;
  uncertain_opens: number;
  possible_human_opens: number;
  clicks: number;
  image_loads: number;
  pdf_accesses: number;
  downloads: number;
  unsubscribes: number;
  open_rate: number;
  click_rate: number;
  campaign: Campaign;
  assets: AssetActivity[];
  timeline: Array<{
    id: string;
    email_id: string;
    recipient_email: string | null;
    event_type: string;
    classification: string | null;
    confidence: number | null;
    classification_reasons: string[];
    created_at: string;
    metadata_json: Record<string, unknown>;
    filename: string | null;
  }>;
};

export type LiveEvent = {
  id?: string;
  type: string;
  campaign_id?: string;
  email_id?: string;
  destination_url?: string;
  recipient_email?: string;
  created_at?: string;
  classification?: string;
  confidence?: number;
  reasons?: string[];
  is_first_unique_open?: boolean;
  filename?: string;
  kind?: string;
  asset_id?: string;
  download?: boolean;
};

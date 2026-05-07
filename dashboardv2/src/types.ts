export type JobStatus = 'saved' | 'applied' | 'interviewing' | 'offer' | 'rejected';

export interface Job {
  id: string;
  company: string;
  role: string;
  location: string;
  salary?: string;
  status: JobStatus;
  dateAdded: string;
  logoUrl?: string;
  source?: 'linkedin' | 'indeed' | 'glassdoor' | 'company_site' | 'other';
  contacts?: Contact[];
  description?: string;
  notes?: string;
  url?: string;
  techStack?: string[];
  umbrellaId?: string;
  umbrellaName?: string;
  companyId?: string;
  matchScore?: number;
  listingAlive?: boolean;
  listingDiedAt?: string;
}

export interface Contact {
  id: string;
  name: string;
  role: string;
  email: string;
  phoneNumber?: string;
  linkedin?: string;
}

export type EmailClassification = 'interview' | 'rejection' | 'action_item' | 'update';

export interface Email {
  id: string;
  gmailMessageId?: string;
  threadId?: string;
  jobId: string;
  sender: string;
  senderEmail?: string;
  subject: string;
  snippet: string;
  body?: string;
  date: string;
  classification: EmailClassification;
  read: boolean;
  type?: 'decision' | 'conversation';
  requiresFollowUp?: boolean;
  lastResponseAt?: string;
  isFromUser?: boolean;
  companyName?: string;
  companyLogoUrl?: string;
  senderDomain?: string;
  confidence?: number;
  summary?: string;
  category?: string;
  colorCode?: string;
  inPipeline?: boolean;
  resolved?: boolean;
  hidden?: boolean;
  collapsed?: boolean;
  actionUrl?: string;
}

export interface ApplicationSuggestionEvidence {
  email_id: string;
  subject: string | null;
  sender: string | null;
  sender_email: string | null;
  received_at: string | null;
  snippet: string | null;
  classification: string | null;
}

export interface ApplicationSuggestion {
  suggestion_key: string;
  company: string;
  role_title: string;
  status: JobStatus;
  source: Job['source'];
  job_url: string | null;
  location?: string | null;
  notes?: string | null;
  email_ids: string[];
  email_count: number;
  latest_email_at: string | null;
  confidence: number;
  evidence: ApplicationSuggestionEvidence[];
  existing_application?: Job | null;
}

export interface InterviewSuggestion {
  email_id: string;
  subject: string | null;
  sender: string | null;
  sender_email: string | null;
  company_name: string | null;
  role_title: string | null;
  application_id: string | null;
  interview_type: string;
  scheduled_at: string | null;
  duration_minutes: number | null;
  location_or_link: string | null;
  snippet: string | null;
  received_at: string | null;
  confidence: number;
}

export interface NetworkSuggestion {
  email_id: string;
  name: string | null;
  email: string;
  title: string | null;
  company: string | null;
  linkedin_url: string | null;
  email_count: number;
  last_interaction_at: string | null;
  subject: string | null;
  snippet: string | null;
}

export type EmailFeedbackAction = 'not_relevant' | 'move_to_inbox' | 'move_to_conversation';

export interface EmailFeedbackPayload {
  email_id: string;
  is_job_related: boolean;
  feedback_action?: EmailFeedbackAction;
  corrected_route?: 'filter' | 'application_inbox' | 'conversation';
  corrected_subtype?: string;
  feedback_label?: string;
  source_surface?: string;
  notes?: string;
}

export interface ResearchProfile {
  id: string;
  name: string;
  objective?: string;
  selected_domains: string[];
  selected_roles: string[];
  selected_companies: string[];
  keywords: string[];
  excluded_keywords: string[];
  source_types: string[];
  mode: 'internal' | 'research' | 'hybrid';
  frequency: 'manual' | 'daily' | 'weekly' | 'biweekly' | 'monthly';
  depth: 'quick' | 'standard' | 'deep';
  notification_mode: 'in_app' | 'email_digest';
  minimum_score: number;
  target_locations: string[];
  remote_types: string[];
  seniority_levels: string[];
  research_source_scopes: string[];
  use_profile_context: boolean;
  include_public_web_research: boolean;
  report_prompt_notes?: string | null;
  max_search_queries: number;
  max_sources_per_run: number;
  active: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_successful_run_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OpportunityScore {
  total_score: number;
  role_fit: number;
  domain_fit: number;
  company_interest: number;
  recency: number;
  public_data_buildability: number;
  outreach_path_strength: number;
  portfolio_gap_relevance: number;
  source_confidence: number;
  explanation?: string;
}

export interface OpportunitySignal {
  id: string;
  profile_id?: string;
  company_id?: string;
  application_id?: string;
  event_type: string;
  title: string;
  summary?: string;
  evidence: Array<{
    url?: string;
    field?: string;
    confidence?: number;
    source_type?: string;
    source_name?: string;
    title?: string;
    excerpt?: string;
  }>;
  domains: string[];
  roles: string[];
  tech_stack: string[];
  confidence: number;
  occurred_at?: string;
  score?: OpportunityScore;
}

export interface OpportunityBrief {
  id: string;
  profile_id?: string;
  run_id?: string;
  signal_id?: string;
  title: string;
  brief_type: string;
  markdown?: string;
  structured_json?: any;
  confidence: number;
  created_at: string;
}

export interface RecommendedAction {
  id: string;
  profile_id?: string;
  signal_id?: string;
  brief_id?: string;
  company_id?: string;
  action_type: string;
  title: string;
  body?: string;
  payload?: any;
  priority: number;
  status: 'open' | 'accepted' | 'dismissed' | 'completed';
  due_at?: string;
  created_at: string;
  completed_at?: string | null;
}

export interface ResearchRun {
  id: string;
  profile_id: string;
  run_type: string;
  mode?: string | null;
  trigger_reason?: string | null;
  status: string;
  orchestrator_version?: string | null;
  graph_thread_id?: string | null;
  current_step?: string | null;
  report_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  source_counts?: Record<string, number>;
  signal_counts?: Record<string, number>;
  error_message?: string | null;
  status_detail?: Record<string, unknown>;
  tokens_in?: number | null;
  tokens_out?: number | null;
  llm_call_count?: number | null;
  cost_estimate_cents?: number | null;
  created_at?: string | null;
}

export interface ResearchRunStep {
  id: string;
  run_id: string;
  profile_id?: string | null;
  step_name: string;
  step_order: number;
  status: string;
  model_name?: string | null;
  prompt_version?: string | null;
  tool_name?: string | null;
  input_json?: Record<string, unknown>;
  output_json?: Record<string, unknown>;
  error_message?: string | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  cost_estimate_cents?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
}

export interface ResearchRunTrace {
  run: ResearchRun;
  step_count: number;
  steps: ResearchRunStep[];
}

export interface ResearchReport {
  id: string;
  profile_id?: string | null;
  run_id?: string | null;
  report_date?: string | null;
  title: string;
  summary_markdown?: string | null;
  structured_json?: Record<string, unknown>;
  diff_summary?: string | null;
  status: string;
  overall_confidence?: number | null;
  finding_count: number;
  source_count: number;
  new_findings_count: number;
  changed_findings_count: number;
  created_at?: string | null;
}

export interface ResearchReportSection {
  id: string;
  report_id: string;
  section_key: string;
  title: string;
  display_order: number;
  markdown?: string | null;
  structured_json?: Record<string, unknown>;
}

export interface ResearchEvidenceItem {
  id: string;
  run_id?: string | null;
  report_id?: string | null;
  profile_id?: string | null;
  source_item_id?: string | null;
  evidence_type: string;
  title?: string | null;
  claim: string;
  snippet?: string | null;
  url?: string | null;
  domain?: string | null;
  company_name?: string | null;
  role_title?: string | null;
  published_at?: string | null;
  confidence?: number | null;
  relevance_score?: number | null;
  novelty_score?: number | null;
  structured_json?: Record<string, unknown>;
  created_at?: string | null;
}

export interface ResearchReportDetail extends ResearchReport {
  sections: ResearchReportSection[];
  evidence: ResearchEvidenceItem[];
  actions: RecommendedAction[];
}

export interface ResearchReportDiff {
  report_id: string;
  profile_id?: string | null;
  status: string;
  diff_summary?: string | null;
  new_findings: string[];
  changed_findings: string[];
  dropped_findings: string[];
  unchanged_findings: string[];
}

export interface RadarFeedbackStats {
  total_feedback: number;
  useful: number;
  not_useful: number;
  usefulness_rate: number;
  notes_count: number;
  recent_feedback: Array<{
    id: string;
    signal_id?: string;
    brief_id?: string;
    action_id?: string;
    report_id?: string;
    run_step_id?: string;
    feedback_scope?: string;
    rating: string;
    notes?: string;
    created_at?: string;
  }>;
}

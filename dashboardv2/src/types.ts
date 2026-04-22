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
  frequency: 'manual' | 'daily' | 'weekly';
  notification_mode: 'in_app' | 'email_digest';
  minimum_score: number;
  active: boolean;
  last_run_at?: string;
  created_at: string;
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
    rating: string;
    notes?: string;
    created_at?: string;
  }>;
}

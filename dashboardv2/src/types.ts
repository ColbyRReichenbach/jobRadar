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

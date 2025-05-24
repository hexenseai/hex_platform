// src/types/index.ts
import React from 'react';

export interface LoginResponse {
    // Django'dan dönen yanıta göre güncelleyin
    message?: string;
    token?: string; // Eğer token tabanlı ise
    // Diğer alanlar...
  }
  
export interface ApiError {
    error?: string;
    detail?: string; // Django REST framework bazen 'detail' kullanır
    // Diğer hata alanları...
  }

  export interface UserInfo {
    fullname: string;
    avatar?: string;
    email?: string;
  }
  
  export interface GptPackageGroupInfo {
    id: string;
    key: string;
    name: string;
    description: string;
  }
  
  export interface GptPackageOption {
    key: string;
    id: string;
    icon?: React.ReactNode;
    label: string;
    is_default: boolean;
    description: string;
    group: GptPackageGroupInfo | null;
  }
  
  export interface UserProfileData {
    id: string;
    user: string;
    company: {
      id: string;
      name: string;
    } | null;
    department: {
      id: string;
      name: string;
    } | null;
    role: {
      id: string;
      name: string;
    } | null;
    phone_number: string;
    avatar?: string | null;
    gpt_preferences: string;
    work_experience_notes: string;
    is_current: boolean;
    gpt_packages: Array<{
      id: string;
      name: string;
      description: string;
      is_default: boolean;
      group: GptPackageGroupInfo | null;
    }>;
  }
  
  export interface WhoAmIResponse {
    id: string;
    username: string;
    email: string;
    profiles: UserProfileData[];
    current_profile: UserProfileData | null;
  }
  
  export interface UserProfileOption {
    value: string;
    label: string;
    gptPackages?: GptPackageOption[];
    avatar?: string;
  }
  
  export interface ChatMessage {
    id: string;
    sender: 'user' | 'assistant' | 'system_error';
    content: string;
    timestamp: Date;
    gptPackageName?: string;
    isStreaming?: boolean;
  }
"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { createClient } from "@/lib/supabase/client";
import type { User, Session } from "@supabase/supabase-js";

interface AuthContextType {
  user: User | null;
  session: Session | null;
  isLoading: boolean;
  conversationId: string | null;
  signInWithEmail: (email: string, password: string) => Promise<{ error: Error | null }>;
  signUpWithEmail: (email: string, password: string) => Promise<{ error: Error | null }>;
  signOut: () => Promise<void>;
  resetConversation: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Generate a unique conversation ID
function generateConversationId(): string {
  return `conv-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const supabase = createClient();

  // Initialize session
  useEffect(() => {
    const initSession = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        setSession(session);
        setUser(session?.user ?? null);

        // Initialize conversation ID when user logs in
        if (session?.user) {
          const storedConvId = localStorage.getItem(`conv_${session.user.id}`);
          if (storedConvId) {
            setConversationId(storedConvId);
          } else {
            const newConvId = generateConversationId();
            localStorage.setItem(`conv_${session.user.id}`, newConvId);
            setConversationId(newConvId);
          }
        }
      } catch (error) {
        console.error("Error getting session:", error);
      } finally {
        setIsLoading(false);
      }
    };

    initSession();

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        console.log("[Auth] State changed:", event);
        setSession(session);
        setUser(session?.user ?? null);

        if (event === "SIGNED_IN" && session?.user) {
          // Get or create conversation ID
          const storedConvId = localStorage.getItem(`conv_${session.user.id}`);
          if (storedConvId) {
            setConversationId(storedConvId);
          } else {
            const newConvId = generateConversationId();
            localStorage.setItem(`conv_${session.user.id}`, newConvId);
            setConversationId(newConvId);
          }
        } else if (event === "SIGNED_OUT") {
          setConversationId(null);
        }
      }
    );

    return () => {
      subscription.unsubscribe();
    };
  }, [supabase.auth]);

  // Sign in with email
  const signInWithEmail = useCallback(async (email: string, password: string) => {
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (error) throw error;
      return { error: null };
    } catch (error) {
      return { error: error as Error };
    }
  }, [supabase.auth]);

  // Sign up with email
  const signUpWithEmail = useCallback(async (email: string, password: string) => {
    try {
      const { error } = await supabase.auth.signUp({
        email,
        password,
      });
      if (error) throw error;
      return { error: null };
    } catch (error) {
      return { error: error as Error };
    }
  }, [supabase.auth]);

  // Sign out
  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, [supabase.auth]);

  // Reset conversation (start new thread)
  const resetConversation = useCallback(() => {
    if (user) {
      const newConvId = generateConversationId();
      localStorage.setItem(`conv_${user.id}`, newConvId);
      setConversationId(newConvId);
    }
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        isLoading,
        conversationId,
        signInWithEmail,
        signUpWithEmail,
        signOut,
        resetConversation,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

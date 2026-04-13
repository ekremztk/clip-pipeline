import { toast as sonnerToast } from "sonner";

export const toast = {
  success: (message: string) =>
    sonnerToast.success(message, { duration: 3500 }),

  error: (message: string) =>
    sonnerToast.error(message, { duration: 4000 }),

  info: (message: string) =>
    sonnerToast(message, { duration: 3500 }),
};

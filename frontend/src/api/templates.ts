import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { toast } from "@/lib/toast";
import type { BrandTemplate, CaptionTemplateInfo } from "./types";

export const brandTemplatesKey = ["brand-templates"] as const;

/** Every caption template with the URL of its preview image. */
export function useCaptionTemplates() {
  return useQuery({
    queryKey: ["caption-templates"],
    queryFn: () => apiFetch<CaptionTemplateInfo[]>("/caption-templates"),
    staleTime: Infinity,
  });
}

/** Every brand template. */
export function useBrandTemplates() {
  return useQuery({
    queryKey: brandTemplatesKey,
    queryFn: () => apiFetch<BrandTemplate[]>("/brand-templates"),
  });
}

/** The font names a brand template can use. */
export function useBrandFonts() {
  return useQuery({
    queryKey: ["brand-fonts"],
    queryFn: () => apiFetch<string[]>("/brand-fonts"),
    staleTime: Infinity,
  });
}

/** Create (no id) or change (PUT) a brand template from a multipart form;
 * the new template is passed to `onSaved`. */
export function useSaveBrandTemplate(onSaved: (saved: BrandTemplate) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, form }: { id: number | null; form: FormData }) =>
      id === null
        ? apiFetch<BrandTemplate>("/brand-templates", {
            method: "POST",
            body: form,
          })
        : apiFetch<BrandTemplate>(`/brand-templates/${id}`, {
            method: "PUT",
            body: form,
          }),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: brandTemplatesKey });
      toast.success(`Saved "${saved.name}".`);
      onSaved(saved);
    },
  });
}

/** Delete a brand template. */
export function useDeleteBrandTemplate(onDeleted: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/brand-templates/${id}`, { method: "DELETE" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: brandTemplatesKey });
      toast.success("Template deleted.");
      onDeleted();
    },
  });
}

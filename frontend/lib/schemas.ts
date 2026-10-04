import { z } from "zod";

/** Client-side response validation for the error envelope. */

export const apiErrorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().nullish()
  }),
  request_id: z.string().nullish(),
  timestamp: z.string()
});

export type ApiErrorEnvelope = z.infer<typeof apiErrorEnvelopeSchema>;

export const pageMetaSchema = z.object({
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  total_pages: z.number(),
  has_next: z.boolean(),
  has_previous: z.boolean()
});

export const severitySchema = z.enum([
  "none",
  "light",
  "moderate",
  "heavy",
  "very_heavy",
  "extreme"
]);

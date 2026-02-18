// frontend/src/services/pdfService.ts

import type { InspectResponse } from "../types";
import { api } from "./api";

export const pdfService = {
  /**
   * Fast inspect: read text layer server-side and extract debtor.name + debtor.inn.
   * MVP endpoint assumption:
   * POST /api/pdfs/inspect  (multipart: files[])
   */
  async inspect(files: File[]): Promise<InspectResponse> {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);

    return api.postForm<InspectResponse>("/api/pdfs/inspect", form);
  },
};

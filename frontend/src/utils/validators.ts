/**
 * Utility functions for validation.
 */

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
const ALLOWED_FILE_TYPES = ['application/pdf'];

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

export function validatePDFFile(file: File): ValidationResult {
  if (!ALLOWED_FILE_TYPES.includes(file.type)) {
    return {
      valid: false,
      error: 'Invalid file type. Only PDF files are allowed.',
    };
  }

  if (file.size > MAX_FILE_SIZE) {
    return {
      valid: false,
      error: `File size exceeds maximum allowed size of ${MAX_FILE_SIZE / 1024 / 1024}MB.`,
    };
  }

  return { valid: true };
}

export function validateBatchSize(fileCount: number): ValidationResult {
  if (fileCount <= 0) {
    return {
      valid: false,
      error: 'Batch must contain at least one file.',
    };
  }

  if (fileCount > 100) {
    return {
      valid: false,
      error: 'Batch size cannot exceed 100 files.',
    };
  }

  return { valid: true };
}

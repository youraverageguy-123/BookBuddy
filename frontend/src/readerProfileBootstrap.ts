import { ApiRequestError } from "./api/client";

export async function ensureReaderProfile(
  storedUserId: string | null,
  createProfile: () => Promise<string>,
  validateProfile: (userId: string) => Promise<unknown>,
): Promise<{ userId: string; created: boolean }> {
  if (!storedUserId) return { userId: await createProfile(), created: true };
  try {
    await validateProfile(storedUserId);
    return { userId: storedUserId, created: false };
  } catch (error) {
    if (!(error instanceof ApiRequestError) || error.status !== 404) throw error;
    return { userId: await createProfile(), created: true };
  }
}

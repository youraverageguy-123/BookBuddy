import { describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "./api/client";
import { ensureReaderProfile } from "./readerProfileBootstrap";

describe("reader profile bootstrap", () => {
  it("replaces a stored profile that disappeared with the backend database", async () => {
    const create = vi.fn(async () => "8d87aef6-f467-4550-b802-bf86d984a0ca");
    const validate = vi.fn(async () => { throw new ApiRequestError(404, "reader profile not found"); });
    await expect(ensureReaderProfile("90d1600d-d824-4c9c-b01d-35011c2bc580", create, validate)).resolves.toEqual({
      userId: "8d87aef6-f467-4550-b802-bf86d984a0ca",
      created: true,
    });
    expect(create).toHaveBeenCalledOnce();
  });

  it("does not replace a profile for transient backend errors", async () => {
    const create = vi.fn(async () => "8d87aef6-f467-4550-b802-bf86d984a0ca");
    const error = new ApiRequestError(503, "backend unavailable");
    await expect(ensureReaderProfile("90d1600d-d824-4c9c-b01d-35011c2bc580", create, async () => { throw error; })).rejects.toBe(error);
    expect(create).not.toHaveBeenCalled();
  });
});

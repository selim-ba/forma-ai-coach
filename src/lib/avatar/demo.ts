/**
 * Kept avatars for demos (made with services/avatar/create_avatar.py --keep from
 * AI-generated photos, so nobody real). The app lists them under "Demo avatars" as a
 * backup when live avatar creation can't run, and never offers to delete them.
 */
export const DEMO_AVATARS: { id: string; label: string }[] = [
  { id: "r-f177221a62c4ce47e371bcd9", label: "Demo man" },
  { id: "r-98d11d26d614845a50ce1f21", label: "Demo woman" },
];

export const isDemoAvatar = (id: string) => DEMO_AVATARS.some((d) => d.id === id);

import { useEffect } from "react";

/**
 * Set the document title and the page's body class while a page is mounted.
 *
 * Args:
 *   title: Document title.
 *   bodyClass: Class that scopes the page's body and link styles in styles.css.
 */
export function usePage(title: string, bodyClass: string): void {
  useEffect(() => {
    document.title = title;
    document.body.classList.add(bodyClass);
    return () => document.body.classList.remove(bodyClass);
  }, [title, bodyClass]);
}

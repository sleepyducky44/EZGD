import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import requests
import json
import os
import threading
import sys
import re

# Configuración
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

HISTORY_FILE = "ezgd_history.json"
GITHUB_API = "https://api.github.com"


class EzGDApp:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("EzGD - Easy Git Downloader")
        self.root.geometry("1100x780")
        self.root.minsize(1000, 700)

        self.history = self.load_history()

        # Estado de descarga
        self.downloading = False
        self.cancel_download = False

        self.setup_ui()

    # ------------------------------------------------------------------ UI ---

    def setup_ui(self):
        ctk.CTkLabel(
            self.root, text="EzGD", font=ctk.CTkFont(size=42, weight="bold")
        ).pack(pady=(30, 5))

        ctk.CTkLabel(
            self.root,
            text="Easy Git Downloader - Descarga lo que necesitas sin complicaciones",
            font=ctk.CTkFont(size=16),
            text_color="gray",
        ).pack(pady=(0, 20))

        # --- URL ---
        url_frame = ctk.CTkFrame(self.root)
        url_frame.pack(fill="x", padx=40, pady=10)

        ctk.CTkLabel(
            url_frame,
            text="Pega el link del repositorio de GitHub aquí:",
            font=ctk.CTkFont(size=16),
        ).pack(anchor="w", padx=20, pady=(15, 5))

        self.url_entry = ctk.CTkEntry(
            url_frame,
            height=50,
            font=ctk.CTkFont(size=16),
            placeholder_text="https://github.com/usuario/proyecto",
        )
        self.url_entry.pack(fill="x", padx=20, pady=(0, 15))
        self.url_entry.bind("<Return>", lambda e: self.search_releases())

        # --- Botón buscar ---
        self.search_btn = ctk.CTkButton(
            self.root,
            text="🔍 BUSCAR DESCARGAS",
            font=ctk.CTkFont(size=20, weight="bold"),
            height=60,
            fg_color="#00C853",
            hover_color="#00B140",
            command=self.search_releases,
        )
        self.search_btn.pack(pady=15, padx=40, fill="x")

        # --- Barra de progreso global ---
        self.progress_bar = ctk.CTkProgressBar(self.root, mode="determinate")
        self.progress_bar.pack(fill="x", padx=40, pady=(0, 5))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(self.root, text="")
        self.progress_label.pack()

        self.cancel_btn = ctk.CTkButton(
            self.root,
            text="❌ Cancelar descarga",
            command=self.cancel_current_download,
            state="disabled",
        )
        self.cancel_btn.pack(pady=(0, 10))

        # --- Historial ---
        hist_frame = ctk.CTkFrame(self.root)
        hist_frame.pack(fill="x", padx=40, pady=5)

        ctk.CTkLabel(
            hist_frame, text="Historial reciente:", font=ctk.CTkFont(size=14)
        ).pack(anchor="w", padx=20, pady=5)

        self.history_combo = ctk.CTkComboBox(
            hist_frame,
            values=self.history[:8],
            width=400,
            command=self.load_from_history,
        )
        self.history_combo.pack(side="left", padx=20, pady=5)

        ctk.CTkButton(
            hist_frame,
            text="🗑️ Borrar historial",
            width=140,
            command=self.clear_history,
        ).pack(side="right", padx=20)

        # --- Frame de resultados ---
        self.result_frame = ctk.CTkScrollableFrame(self.root)
        self.result_frame.pack(fill="both", expand=True, padx=40, pady=20)

    # ------------------------------------------------------------ HISTORIAL ---

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_history(self, repo):
        if repo in self.history:
            self.history.remove(repo)
        self.history.insert(0, repo)
        self.history = self.history[:20]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2)
        self.history_combo.configure(values=self.history[:8])

    def clear_history(self):
        if messagebox.askyesno("Confirmar", "¿Borrar historial?"):
            self.history = []
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            self.history_combo.configure(values=[])

    def load_from_history(self, choice):
        if choice:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, f"https://github.com/{choice}")
            self.search_releases()

    # ------------------------------------------------------------- PARSER ---

    def parse_github_url(self, url):
        url = url.strip()
        if not url:
            return None, None
        url = url.replace("git@github.com:", "https://github.com/")
        if url.endswith(".git"):
            url = url[:-4]
        match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
        if match:
            return match.group(1), match.group(2)
        return None, None

    # ----------------------------------------------------------- SCORING ---
    # Solo para Windows (explícito).

    def get_asset_score(self, name):
        if sys.platform != "win32":
            return 0

        name = name.lower()
        score = 0

        if ".exe" in name or ".msi" in name:
            score += 50
        if "windows" in name or "win64" in name or "win32" in name:
            score += 30
        if "x64" in name or "amd64" in name:
            score += 40
        if "portable" in name:
            score += 20
        if "setup" in name or "installer" in name:
            score += 10

        # Penalizaciones
        if "arm" in name:
            score -= 50
        if "beta" in name or "debug" in name or "alpha" in name:
            score -= 20
        if "source" in name or "src" in name:
            score -= 100

        return score

    def get_recommended_asset(self, assets):
        """Devuelve el asset recomendado o None si no hay uno confiable."""
        if not assets:
            return None
        best = max(assets, key=lambda a: self.get_asset_score(a["name"]))
        if self.get_asset_score(best["name"]) <= 0:
            return None
        return best

    def get_platform_label(self):
        if sys.platform == "win32":
            return "Windows 64-bit"
        elif sys.platform == "darwin":
            return "macOS"
        return "Linux"

    # --------------------------------------------------------------- API ---

    def search_releases(self):
        url = self.url_entry.get().strip()
        owner, repo = self.parse_github_url(url)

        if not owner:
            messagebox.showerror(
                "URL inválida",
                "Asegurate de pegar el link completo de GitHub.\nEjemplo: https://github.com/usuario/proyecto",
            )
            return

        for w in self.result_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self.result_frame, text="🔄 Buscando...", font=ctk.CTkFont(size=18)
        ).pack(pady=40)

        threading.Thread(
            target=self._fetch_releases_thread, args=(owner, repo), daemon=True
        ).start()

    def _fetch_releases_thread(self, owner, repo):
        try:
            headers = {"User-Agent": "EzGD"}
            r = requests.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/releases",
                headers=headers,
                params={"per_page": 10},
                timeout=15,
            )

            if r.status_code == 403:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Límite de GitHub",
                        "GitHub limitó las consultas temporalmente.\nEsperá unos minutos y volvé a intentar.",
                    ),
                )
                self._clear_loading()
                return
            elif r.status_code == 404:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "No encontrado",
                        "Repositorio no encontrado.\nVerificá que el link esté bien escrito.",
                    ),
                )
                self._clear_loading()
                return
            elif r.status_code != 200:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", f"Error al buscar (código {r.status_code})"
                    ),
                )
                self._clear_loading()
                return

            releases = r.json()

            if not releases:
                self.root.after(
                    0,
                    lambda: self._show_no_releases(),
                )
                return

            self.root.after(0, lambda: self._display_releases(owner, repo, releases))

        except requests.exceptions.ConnectionError:
            self.root.after(
                0,
                lambda: messagebox.showerror("Sin conexión", "No se pudo conectar a Internet."),
            )
            self._clear_loading()
        except requests.exceptions.Timeout:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Tiempo agotado",
                    "La búsqueda tardó demasiado.\nVerificá tu conexión.",
                ),
            )
            self._clear_loading()
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error inesperado", str(e)))
            self._clear_loading()

    def _clear_loading(self):
        self.root.after(0, lambda: [w.destroy() for w in self.result_frame.winfo_children()])

    def _show_no_releases(self):
        for w in self.result_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.result_frame,
            text="Este repositorio no tiene versiones publicadas para descargar.",
            text_color="orange",
            font=ctk.CTkFont(size=15),
        ).pack(pady=40)

    # ----------------------------------------------------------- DISPLAY ---

    def _display_releases(self, owner, repo, releases):
        for w in self.result_frame.winfo_children():
            w.destroy()

        self.save_history(f"{owner}/{repo}")

        latest = releases[0]
        older = releases[1:]

        self._render_release(latest, is_latest=True)

        if older:
            ctk.CTkLabel(
                self.result_frame,
                text="── Versiones anteriores ──",
                font=ctk.CTkFont(size=13),
                text_color="gray",
            ).pack(pady=(15, 5))

            for release in older:
                self._render_release(release, is_latest=False)

    def _render_release(self, release, is_latest):
        bg_color = "#1b2e1b" if is_latest else "#202030"
        frame = ctk.CTkFrame(self.result_frame, fg_color=bg_color)
        frame.pack(fill="x", padx=5, pady=(0, 12) if is_latest else (0, 5))

        tag = release.get("tag_name", "Sin versión")
        name = release.get("name") or tag
        is_pre = release.get("prerelease", False)

        header_text = f"📦 {name}"
        if name != tag:
            header_text += f"  ({tag})"
        if is_pre:
            header_text += "  ⚠️ Pre-release"

        ctk.CTkLabel(
            frame,
            text=header_text,
            font=ctk.CTkFont(size=22 if is_latest else 15, weight="bold"),
            text_color="white" if is_latest else "#aaaaaa",
        ).pack(anchor="w", padx=15, pady=(12, 6))

        # Separar binarios de código fuente
        binary_assets = list(release.get("assets", []))

        source_assets = []
        if release.get("zipball_url"):
            source_assets.append(
                {
                    "name": "Source code (.zip)",
                    "browser_download_url": release["zipball_url"],
                    "size": 0,
                }
            )
        if release.get("tarball_url"):
            source_assets.append(
                {
                    "name": "Source code (.tar.gz)",
                    "browser_download_url": release["tarball_url"],
                    "size": 0,
                }
            )

        if not binary_assets and not source_assets:
            ctk.CTkLabel(
                frame,
                text="Este release no tiene archivos adjuntos.",
                text_color="orange",
            ).pack(padx=15, pady=10)
            ctk.CTkLabel(frame, text="").pack(pady=3)
            return

        # --- Binarios ---
        if binary_assets:
            recommended = self.get_recommended_asset(binary_assets)

            if is_latest:
                # Botón grande recomendado (solo en la versión más reciente)
                if recommended:
                    ctk.CTkLabel(
                        frame,
                        text=f"💡 Recomendado para {self.get_platform_label()}:",
                        font=ctk.CTkFont(size=13),
                        text_color="#88dd88",
                    ).pack(anchor="w", padx=15, pady=(4, 2))

                    ctk.CTkButton(
                        frame,
                        text=f"⬇️  DESCARGAR RECOMENDADO  —  {recommended['name']}",
                        font=ctk.CTkFont(size=16, weight="bold"),
                        height=52,
                        fg_color="#00C853",
                        hover_color="#00B140",
                        command=lambda a=recommended: self.download_asset(a),
                    ).pack(fill="x", padx=15, pady=(2, 10))
                else:
                    ctk.CTkLabel(
                        frame,
                        text=(
                            "⚠️ No se detectó un archivo recomendado automáticamente.\n"
                            "Elegí el que corresponda a tu sistema desde la lista de abajo."
                        ),
                        text_color="orange",
                        font=ctk.CTkFont(size=13),
                        justify="left",
                    ).pack(anchor="w", padx=15, pady=(4, 8))

            # Lista completa de binarios
            section_text = "Todos los archivos disponibles:" if is_latest else "Archivos:"
            ctk.CTkLabel(
                frame,
                text=section_text,
                font=ctk.CTkFont(size=12),
                text_color="#999999",
            ).pack(anchor="w", padx=15, pady=(4, 2))

            for asset in binary_assets:
                is_rec = recommended is not None and asset["name"] == recommended["name"]
                size_bytes = asset.get("size", 0)
                size_text = f"  ({size_bytes / 1024 / 1024:.1f} MB)" if size_bytes > 0 else ""
                rec_badge = "  ✅ Recomendado" if is_rec else ""

                ctk.CTkButton(
                    frame,
                    text=f"⬇️  {asset['name']}{size_text}{rec_badge}",
                    fg_color="#1a4a1a" if is_rec else "transparent",
                    border_color="#00C853" if is_rec else "#555555",
                    border_width=1,
                    text_color="white" if is_rec else "#cccccc",
                    anchor="w",
                    command=lambda a=asset: self.download_asset(a),
                ).pack(fill="x", padx=15, pady=2)

        # --- Código fuente ---
        if source_assets:
            ctk.CTkLabel(
                frame,
                text=(
                    "📄 Código fuente  —  Solo para desarrolladores.\n"
                    "        ⚠️ Estos archivos NO son programas. No los descargues si no sabés qué son."
                ),
                font=ctk.CTkFont(size=11),
                text_color="#666666",
                justify="left",
            ).pack(anchor="w", padx=15, pady=(14, 3))

            for src in source_assets:
                ctk.CTkButton(
                    frame,
                    text=f"⬇️  {src['name']}",
                    fg_color="transparent",
                    border_color="#444444",
                    border_width=1,
                    text_color="#666666",
                    anchor="w",
                    command=lambda a=src: self.download_asset(a),
                ).pack(fill="x", padx=15, pady=2)

        ctk.CTkLabel(frame, text="").pack(pady=4)

    # ---------------------------------------------------------- DESCARGA ---

    def download_asset(self, asset):
        if self.downloading:
            messagebox.showinfo(
                "Descarga en curso",
                "Ya hay una descarga activa.\nEsperá que termine o cancelala primero.",
            )
            return

        path = filedialog.asksaveasfilename(initialfile=asset["name"])
        if not path:
            return

        self.downloading = True
        self.cancel_download = False
        self.cancel_btn.configure(state="normal")
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Iniciando descarga...")

        def run():
            url = asset["browser_download_url"]

            try:
                with requests.get(url, stream=True, timeout=(15, None)) as r:
                    r.raise_for_status()

                    total = int(r.headers.get("content-length", 0))
                    has_total = total > 0
                    done = 0

                    # Sin content-length: barra animada
                    if not has_total:
                        self.root.after(
                            0,
                            lambda: self.progress_bar.configure(mode="indeterminate"),
                        )
                        self.root.after(0, lambda: self.progress_bar.start())

                    with open(path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if self.cancel_download:
                                break

                            if chunk:  # Ignorar chunks vacíos
                                f.write(chunk)
                                done += len(chunk)

                                if has_total:
                                    percent = done / total
                                    mb_done = done // 1024 // 1024
                                    mb_total = total // 1024 // 1024
                                    self.root.after(
                                        0,
                                        lambda p=percent: self.progress_bar.set(p),
                                    )
                                    self.root.after(
                                        0,
                                        lambda d=mb_done, t=mb_total: self.progress_label.configure(
                                            text=f"Descargando...  {d} MB / {t} MB"
                                        ),
                                    )
                                else:
                                    mb_done = done // 1024 // 1024
                                    self.root.after(
                                        0,
                                        lambda d=mb_done: self.progress_label.configure(
                                            text=f"Descargando...  {d} MB"
                                        ),
                                    )

                # Después del with open — evaluar resultado
                if self.cancel_download:
                    if os.path.exists(path):
                        os.remove(path)
                    self.root.after(
                        0,
                        lambda: self.progress_label.configure(text="Descarga cancelada."),
                    )
                else:
                    self.root.after(0, lambda: self.progress_bar.set(1))
                    self.root.after(
                        0,
                        lambda: self.progress_label.configure(text="✅ Descarga completa"),
                    )
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "¡Listo!", f"Archivo guardado en:\n{path}"
                        ),
                    )

            except requests.exceptions.HTTPError as e:
                if os.path.exists(path):
                    os.remove(path)
                code = e.response.status_code if e.response else "?"
                msg = (
                    "GitHub limitó las consultas.\nIntentá más tarde."
                    if code == 403
                    else f"Error al descargar (código HTTP {code})"
                )
                self.root.after(0, lambda: messagebox.showerror("Error", msg))
                self.root.after(
                    0, lambda: self.progress_label.configure(text="Error en la descarga.")
                )

            except requests.exceptions.ConnectionError:
                if os.path.exists(path):
                    os.remove(path)
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Sin conexión", "Se perdió la conexión durante la descarga."
                    ),
                )
                self.root.after(
                    0, lambda: self.progress_label.configure(text="Error: sin conexión.")
                )

            except Exception as e:
                if os.path.exists(path):
                    os.remove(path)
                self.root.after(0, lambda: messagebox.showerror("Error inesperado", str(e)))
                self.root.after(
                    0, lambda: self.progress_label.configure(text="Error en la descarga.")
                )

            finally:
                self.downloading = False
                self.cancel_download = False
                # Restaurar barra a modo normal
                self.root.after(0, lambda: self.progress_bar.stop())
                self.root.after(
                    0, lambda: self.progress_bar.configure(mode="determinate")
                )
                self.root.after(
                    0, lambda: self.cancel_btn.configure(state="disabled")
                )
                # Limpiar barra y label después de 3 segundos
                self.root.after(3000, lambda: self.progress_bar.set(0))
                self.root.after(3000, lambda: self.progress_label.configure(text=""))

        threading.Thread(target=run, daemon=True).start()

    def cancel_current_download(self):
        self.cancel_download = True
        self.progress_label.configure(text="Cancelando...")


if __name__ == "__main__":
    app = EzGDApp()
    app.root.mainloop()

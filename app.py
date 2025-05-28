import os
import datetime
import requests
import telebot
import time
import json
import pytz
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


class WebScraper:
    # ========================== CONFIGURAÇÕES BÁSICAS ==========================
    WEBHOOK_URL = "https://automacao-stk-n8n.b6dfdz.easypanel.host/webhook/Blaze_Crash"

    # FIGURINHAS
    STK_FECHA_DIA      = "CAACAgEAAxkBAAEMJ11mS6F8u4rDdUuKo9y6XObYTpmCtgACvgEAAsFWwUVjxQN4wmmSBDUE"   # sala fechada
    STK_ABRE_DIA       = "CAACAgEAAxkBAAE1f5JoNsHKVCTUbWPWZe_TDEoaYQsU5QACbAQAAl4ByUUIjW-sdJsr6DYE"   # sala aberta
    STK_WIN_SEM_GALE   = "CAACAgEAAxkBAAE1f6doNsL-F7PTY9JjIycLkFIVATMLpAAC0QAD7EWAR6BQIQgy2mgWNgQ"   # win sem gale
    STK_WIN_GALE       = "CAACAgEAAxkBAAE1f61oNsM54vzDVgv3Cg_uUp1usAQnPAAC_AADQSaBR11zLQEy5HO0NgQ"   # win gale 1/2
    STK_LOSS           = "CAACAgEAAxkBAAE1f8VoNsObInY9BYEvoGFnaysiVo9U0QACBAQAAn7ngAJKFrRni2QyVjYE"   # loss

    def __init__(self):
        # -------- EDITÁVEIS --------
        self.game = "Modo Crash 🚀"

        # Lê o token do ambiente
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("Variável de ambiente TELEGRAM_BOT_TOKEN não definida!")

        # Lê os chat IDs do ambiente
        chat_ids_env = os.getenv("CHAT_IDS")
        if chat_ids_env:
            self.chat_ids = [id.strip() for id in chat_ids_env.split(",")]
        else:
            raise ValueError("Variável de ambiente CHAT_IDS não definida!")

        self.url_API = "https://elmovimiento.vip/blaze_crash/luk/index.json"
        self.gales = 1

        # -------- VARIÁVEIS DE ESTATÍSTICAS GERAIS --------
        self.win_results = 0
        self.loss_results = 0
        self.win_first_try = 0
        self.win_gale1 = 0
        self.win_gale2 = 0
        self.win_streak = 0
        self.max_streak = 0

        # -------- ESTATÍSTICAS POR ESTRATÉGIA (simples) --------
        # exemplo: {"E1": {"enviada":1,"win_primeira":1,"win_gale1":0,"derrotas":0}}
        self.estrategias_stats = {}
        self.current_estrategia = None

        # -------- CONTROLES DO BOT --------
        self.count = 0
        self.analisar = True
        self.alvo = 0

        # Para gerenciamento de alertas
        self.last_message_ids_by_group = {}
        self.message_delete = False

        # Inicializa o bot
        self.bot = telebot.TeleBot(token=self.token, parse_mode="html")

        # Datas
        brasilia_tz = pytz.timezone("America/Sao_Paulo")
        self.check_date = datetime.datetime.now(brasilia_tz).strftime("%d/%m/%Y")

    # =====================================================================
    # FUNÇÕES "SEGURAS" DE ENVIO
    # =====================================================================
    def send_webhook(self, payload: dict):
        try:
            requests.post(self.WEBHOOK_URL, json=payload, timeout=10)
        except Exception as e:
            print(f"Erro webhook: {e}")

    def safe_send_message(self, chat_id, text, **kwargs):
        try:
            msg = self.bot.send_message(chat_id, text, **kwargs)
            self.send_webhook({"evento": "mensagem_telegram", "chat_id": chat_id, "texto": text})
            return msg
        except Exception as e:
            if "need administrator rights" in str(e):
                print(f"[AVISO] Bot sem permissões no grupo {chat_id}, ignorando envio.")
            else:
                print(f"[ERRO] Falha ao enviar mensagem para {chat_id}: {e}")
            return None

    def safe_send_sticker(self, chat_id, sticker):
        try:
            msg = self.bot.send_sticker(chat_id, sticker=sticker)
            self.send_webhook({"evento": "sticker_telegram", "chat_id": chat_id, "sticker": sticker})
            return msg
        except Exception as e:
            if "need administrator rights" in str(e):
                print(f"[AVISO] Bot sem permissões no grupo {chat_id}, ignorando sticker.")
            else:
                print(f"[ERRO] Falha ao enviar sticker para {chat_id}: {e}")
            return None

    def safe_delete_message(self, chat_id, message_id):
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception as e:
            if "need administrator rights" in str(e):
                print(f"[AVISO] Bot sem perms para deletar no grupo {chat_id}, ignorando.")
            else:
                print(f"[ERRO] Falha ao deletar mensagem em {chat_id}: {e}")

    # =====================================================
    # RESET DIÁRIO
    # =====================================================
    def restart(self):
        brasilia_tz = pytz.timezone("America/Sao_Paulo")
        current_date = datetime.datetime.now(brasilia_tz).strftime("%d/%m/%Y")

        if current_date != self.check_date:
            print(f"🗓 Novo dia detectado: {current_date}. Reiniciando contadores…")
            self.check_date = current_date

            # FECHA DIA
            for g_id in self.chat_ids:
                self.safe_send_sticker(g_id, self.STK_FECHA_DIA)
            self.results()  # placar final do dia
            self.print_stats()

            # Zera contadores gerais
            self.win_results = self.loss_results = 0
            self.win_first_try = self.win_gale1 = self.win_gale2 = 0
            self.win_streak = self.max_streak = 0
            # Zera estatísticas por estratégia
            self.estrategias_stats = {}

            time.sleep(60)  # espera 1 minuto

            # ABRE NOVO DIA
            for g_id in self.chat_ids:
                self.safe_send_sticker(g_id, self.STK_ABRE_DIA)
                self.safe_send_message(
                    g_id, "🚀 <b>NOVO DIA INICIADO!</b> Estatísticas zeradas.", parse_mode="html"
                )
            self.results()

    # ===========================================
    # FUNÇÃO DE RESULTADOS (placar para os grupos)
    # ===========================================
    def results(self):
        total = self.win_results + self.loss_results
        win_hate = f"{(100 * self.win_results / total):.2f}%" if total else "0.00%"

        placar = (
            "<b>🏆 Placar Atual 🏆</b>\n"
            f"🥇 <b>Vitórias de Primeira:</b> {self.win_first_try}\n"
            f"🥈 <b>Vitórias Gale 1:</b> {self.win_gale1}\n"
            f"💚 <b>Total de Vitórias:</b> {self.win_results}\n"
            f"💔 <b>Loss:</b> {self.loss_results}\n"
            f"🎯 <b>Assertividade:</b> {win_hate}\n"
            f"♻️ <b>Sequência Máxima:</b> {self.max_streak}\n"
        )
        for g_id in self.chat_ids:
            self.safe_send_message(g_id, placar, parse_mode="html")

    # ---------- estatísticas simplificadas (console) ----------
    def print_stats(self):
        txt = "\n🔥 Estatísticas das Estratégias 🔥\n"
        for est in sorted(self.estrategias_stats.keys(), key=lambda x: int(x[1:])):
            st = self.estrategias_stats[est]
            assertv = (
                (st["win_primeira"] + st["win_gale1"]) / st["enviada"] * 100
                if st["enviada"]
                else 0
            )
            txt += (
                f"{est}: enviadas {st['enviada']} | "
                f"win1ª {st['win_primeira']} | "
                f"winG1 {st['win_gale1']} | "
                f"loss {st['derrotas']} | "
                f"assert {assertv:.1f}%\n"
            )
        print(txt)

    # ========= ALERTA DE GALE (e depois deletar) =========
    def alert_gale(self):
        for g_id in self.chat_ids:
            msg = self.safe_send_message(
                g_id, f"<b>Utilizar {self.count}º Gale</b> 🚨", parse_mode="html"
            )
            if msg:
                self.last_message_ids_by_group[g_id] = msg.message_id
        self.message_delete = True

    def delete(self):
        if self.message_delete:
            for g_id, msg_id in list(self.last_message_ids_by_group.items()):
                self.safe_delete_message(g_id, msg_id)
            self.message_delete = False
            self.last_message_ids_by_group.clear()

    # =========== ENVIO DE SINAL ===========
    def send_sinal(self, finalnum, estrategia_nome):
        self.analisar = False
        self.current_estrategia = estrategia_nome

        # inicializa dicionário da estratégia se necessário
        if estrategia_nome not in self.estrategias_stats:
            self.estrategias_stats[estrategia_nome] = {
                "enviada": 0,
                "win_primeira": 0,
                "win_gale1": 0,
                "derrotas": 0,
            }
        self.estrategias_stats[estrategia_nome]["enviada"] += 1

        print(f"💥 {estrategia_nome} | Palpite {self.alvo}x após {finalnum}x 💥")

        mensagem = (
            "<b>Palpite Confirmado 💥</b>\n\n"
            f"🎯 <b>Palpite para:</b> {self.alvo}x\n"
            f"🎰 <b>Entrada após:</b> {finalnum}x\n"
            f"🐔 <b>Utilizar até {self.gales} Gales</b>\n\n"
            f"<b>{self.game}</b>"
        )

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Plataforma 📱", url="https://elmovimiento.vip/cadastro-blaze"),
            InlineKeyboardButton("Links Úteis 💎", url="https://ciainvestimentos.com"),
        )

        for g_id in self.chat_ids:
            msg = self.safe_send_message(g_id, mensagem, reply_markup=markup, parse_mode="html")
            if msg:
                self.last_message_ids_by_group[g_id] = msg.message_id

    # ===================== MARTINGALE =====================
    def martingale(self, resultado, finalnum):
        # ---------- WIN ----------
        if resultado == "WIN":
            self.win_results += 1
            self.win_streak += 1
            self.max_streak = max(self.max_streak, self.win_streak)

            if self.count == 0:
                self.win_first_try += 1
                self.estrategias_stats[self.current_estrategia]["win_primeira"] += 1
                sticker = self.STK_WIN_SEM_GALE
                message_txt = f"<b>Win Sem Gale ✅ | Vitória em {finalnum:.2f}x ✅</b>"
            else:  # Gale 1
                self.win_gale1 += 1
                self.estrategias_stats[self.current_estrategia]["win_gale1"] += 1
                sticker = self.STK_WIN_GALE
                message_txt = f"<b>Win Gale 1 ✅ | Vitória em {finalnum:.2f}x ✅</b>"

            for g_id in self.chat_ids:
                self.safe_send_sticker(g_id, sticker)
                self.safe_send_message(g_id, message_txt, parse_mode="html")

        # ---------- LOSS ----------
        else:
            self.count += 1
            if self.count > self.gales:
                self.loss_results += 1
                self.win_streak = 0
                self.estrategias_stats[self.current_estrategia]["derrotas"] += 1
                for g_id in self.chat_ids:
                    self.safe_send_sticker(g_id, self.STK_LOSS)
                    self.safe_send_message(g_id, "<b>LOSS ❌</b>", parse_mode="html")
            else:
                self.alert_gale()
                return  # ainda na sequência de gales

        # ---------- ENCERRA CICLO ----------
        self.count = 0
        self.analisar = True
        self.delete()   # limpa alertas pendentes
        self.results()  # placar em tempo real
        self.print_stats()
        self.restart()

    # ===================== CHECAGEM DE RESULTADO =====================
    def check_results(self, results):
        if results[0] >= self.alvo:
            self.martingale("WIN", results[0])
        else:
            self.martingale("LOSS", results[0])

    # ===================== LOOP PRINCIPAL =====================
    def start(self):
        check = []
        while True:
            try:
                time.sleep(1)
                self.restart()  # verifica virada de dia

                resp = requests.get(self.url_API, timeout=10)
                resp.raise_for_status()
                json_data = resp.json()

                crash_points = [float(item["crash_point"]) for item in json_data]

                if crash_points != check and len(crash_points) > 6:
                    check = crash_points
                    print(f"[{', '.join(map(str, crash_points[:20]))}]")
                    self.delete()  # remove alertas anteriores
                    self.estrategy(crash_points)

            except Exception as e:
                print(f"[ERRO] {e}")

    # ===================== ESTRATÉGIAS (apenas manuais) =====================
    def estrategy(self, results):
        # Se já existe palpite em jogo, verifica WIN / LOSS
        if not self.analisar:
            self.check_results(results)
            return

        # --------- SINAL MANUAL ---------
# ---------- E1 ----------
        if (
            len(results) >= 13
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] >= 2.0
            and results[6] >= 2.0
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] <= 1.99
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E1")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E3 ----------
        if (
            len(results) >= 13
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] <= 1.99
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E3")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E5 ----------
        if (
            len(results) >= 12
            and results[0] >= 2.0
            and results[1] >= 2.0
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] >= 2.0
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] <= 1.99
            and results[11] >= 2.0
        ):
            print("SINAL ENCONTRADO! E5")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E6 ----------
        if (
            len(results) >= 12
            and results[0] >= 2.0
            and results[1] >= 2.0
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] >= 2.0
            and results[7] >= 2.0
            and results[8] <= 1.99
            and results[9] <= 1.99
            and results[10] >= 2.0
            and results[11] >= 2.0
        ):
            print("SINAL ENCONTRADO! E6")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E7 ----------
        if (
            len(results) >= 13
            and results[0] >= 2.0
            and results[1] >= 2.0
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] >= 2.0
            and results[7] >= 2.0
            and results[8] <= 1.99
            and results[9] <= 1.99
            and results[10] >= 2.0
            and results[11] <= 1.99
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E7")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E8 ----------
        if (
            len(results) >= 12
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] >= 2.0
            and results[6] >= 2.0
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] <= 1.99
            and results[11] <= 1.99
        ):
            print("SINAL ENCONTRADO! E8")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E9 ----------
        if (
            len(results) >= 11
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] >= 2.0
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] <= 1.99
        ):
            print("SINAL ENCONTRADO! E9")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E11 ----------
        if (
            len(results) >= 11
            and results[0] >= 2.0
            and results[1] >= 2.0
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] >= 2.0
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] <= 1.99
            and results[10] >= 2.0
        ):
            print("SINAL ENCONTRADO! E11")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E12 ----------
        if (
            len(results) >= 13
            and results[0] <= 1.99
            and results[1] >= 2.0
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] <= 1.99
            and results[11] <= 1.99
            and results[12] >= 2.0
        ):
            print("SINAL ENCONTRADO! E12")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E13 ----------
        if (
            len(results) >= 12
            and results[0] <= 1.99
            and results[1] >= 2.0
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] >= 2.0
        ):
            print("SINAL ENCONTRADO! E13")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E14 ----------
        if (
            len(results) >= 13
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] >= 2.0
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] >= 2.0
            and results[11] <= 1.99
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E14")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E16 ----------
        if (
            len(results) >= 10
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] >= 2.0
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] <= 1.99
        ):
            print("SINAL ENCONTRADO! E16")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E17 ----------
        if (
            len(results) >= 13
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] <= 1.99
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E17")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E18 ----------
        if (
            len(results) >= 12
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] <= 1.99
        ):
            print("SINAL ENCONTRADO! E18")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E19 ----------
        if (
            len(results) >= 13
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] >= 2.0
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E19")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E20 ----------
        if (
            len(results) >= 13
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] <= 1.99
            and results[11] >= 2.0
            and results[12] >= 2.0
        ):
            print("SINAL ENCONTRADO! E20")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E21 ----------
        if (
            len(results) >= 13
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] >= 2.0
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] >= 2.0
            and results[11] <= 1.99
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E21")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E23 ----------
        if (
            len(results) >= 13
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] >= 2.0
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] <= 1.99
            and results[11] >= 2.0
            and results[12] >= 2.0
        ):
            print("SINAL ENCONTRADO! E23")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E24 ----------
        if (
            len(results) >= 12
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] >= 2.0
            and results[11] >= 2.0
        ):
            print("SINAL ENCONTRADO! E24")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E25 ----------
        if (
            len(results) >= 13
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] >= 2.0
            and results[6] >= 2.0
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] >= 2.0
            and results[11] <= 1.99
            and results[12] >= 2.0
        ):
            print("SINAL ENCONTRADO! E25")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E28 ----------
        if (
            len(results) >= 13
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] >= 2.0
            and results[7] >= 2.0
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] >= 2.0
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E28")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E29 ----------
        if (
            len(results) >= 12
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] <= 1.99
            and results[10] <= 1.99
            and results[11] >= 2.0
        ):
            print("SINAL ENCONTRADO! E29")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return

# ===================== EXECUÇÃO =====================
if __name__ == "__main__":
    bot = WebScraper()
    bot.start()

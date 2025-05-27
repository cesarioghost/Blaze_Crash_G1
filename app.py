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

    # FIGURINHAS (mesmas do bot de Double: troque se desejar)
    STK_FECHA_DIA = "CAACAgEAAxkBAAEMJ11mS6F8u4rDdUuKo9y6XObYTpmCtgACvgEAAsFWwUVjxQN4wmmSBDUE"
    STK_ABRE_DIA = "CAACAgEAAxkBAAEMJ3dmUOJkY1I3G-fbOfUqJzJrEUK3SAACZAEAAladvUWiPv-Ml0JTGjUE"
    STK_WIN_SEM_GALE = "CAACAgEAAxkBAAEMJ09mS6EpSDYdGIoirTFSct6Mj09yOwACLgIAAhlf8UWPCaYRIAn6WjUE"
    STK_WIN_GALE      = "CAACAgEAAxkBAAEMJ1NmS6FXeVVF6gABCwvlA0UGDF1oq_8AAmECAALzR_BFho1sbO1a4rs1BA"
    STK_LOSS          = "CAACAgEAAxkBAAEMJ1lmS6FrwQoDeT4NF4nSIYwxXaMHtAACNgIAAlq7-UU85F0_EghOBDUE"

    def __init__(self):
        # -------- EDITÁVEIS --------
        self.game = "Modo Crash 🚀"

        # Lê o token do ambiente (configure TELEGRAM_BOT_TOKEN no Railway)
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("Variável de ambiente TELEGRAM_BOT_TOKEN não definida!")

        # Lê os chat IDs do ambiente (configure CHAT_IDS, ex.: "-1002381442124, -1001931486076")
        chat_ids_env = os.getenv("CHAT_IDS")
        if chat_ids_env:
            self.chat_ids = [id.strip() for id in chat_ids_env.split(",")]
        else:
            raise ValueError("Variável de ambiente CHAT_IDS não definida!")

        self.url_API = "https://elmovimiento.vip/blaze_crash/luk/index.json"
        self.gales = 1
        self.link = ""

        # -------- VARIÁVEIS DE ESTATÍSTICAS --------
        self.win_results = 0
        self.loss_results = 0
        self.max_hate = 0                 # sequência atual de vitórias
        self.win_hate = 0                 # assertividade em %
        self.win_first_try = 0
        self.win_gale1 = 0
        self.win_gale2 = 0
        self.win_streak = 0
        self.max_streak = 0
        self.total_palpites = 0

        # -------- CONTROLES DO BOT --------
        self.count = 0
        self.analisar = True
        self.alvo = 0

        # Para gerenciar mensagens (ex.: alert) que precisem ser deletadas
        self.last_message_ids_by_group = {}
        self.message_delete = False

        # Inicializa o bot
        self.bot = telebot.TeleBot(token=self.token, parse_mode="html")

        # Datas
        brasilia_tz = pytz.timezone("America/Sao_Paulo")
        self.check_date = datetime.datetime.now(brasilia_tz).strftime("%d/%m/%Y")

    # =====================================================================
    # FUNÇÕES "SEGURAS" DE ENVIO (ignoram falta de permissão e logam webhook)
    # =====================================================================
    def send_webhook(self, payload: dict):
        try:
            requests.post(self.WEBHOOK_URL, json=payload, timeout=10)
        except Exception as e:
            print(f"Erro webhook: {e}")

    def safe_send_message(self, chat_id, text, **kwargs):
        try:
            msg = self.bot.send_message(chat_id, text, **kwargs)
            self.send_webhook(
                {"evento": "mensagem_telegram", "chat_id": chat_id, "texto": text}
            )
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
            self.send_webhook(
                {"evento": "sticker_telegram", "chat_id": chat_id, "sticker": sticker}
            )
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
    # RESET DIÁRIO (fecha dia, gera placar final, abre novo)
    # =====================================================
    def restart(self):
        brasilia_tz = pytz.timezone("America/Sao_Paulo")
        current_date = datetime.datetime.now(brasilia_tz).strftime("%d/%m/%Y")

        if current_date != self.check_date:
            print(f"🗓 Novo dia detectado: {current_date}. Reiniciando contadores…")
            self.check_date = current_date

            # --- FECHA DIA ---
            for g_id in self.chat_ids:
                self.safe_send_sticker(g_id, self.STK_FECHA_DIA)
            self.results()  # placar final do dia

            # Zera contadores
            self.win_results = self.loss_results = 0
            self.max_hate = self.win_hate = 0
            self.win_first_try = self.win_gale1 = self.win_gale2 = 0
            self.win_streak = self.max_streak = 0
            self.total_palpites = 0

            time.sleep(60)  # espera 1 minuto para reabrir

            # --- ABRE NOVO DIA ---
            for g_id in self.chat_ids:
                self.safe_send_sticker(g_id, self.STK_ABRE_DIA)
                self.safe_send_message(
                    g_id, "🚀 <b>NOVO DIA INICIADO!</b> Estatísticas zeradas.", parse_mode="html"
                )
            self.results()  # placar zerado

    # ===========================================
    # FUNÇÃO DE RESULTADOS (placar para os grupos)
    # ===========================================
    def results(self):
        total = self.win_results + self.loss_results
        self.win_hate = f"{(100 * self.win_results / total):.2f}%" if total else "0.00%"

        placar = (
            "<b>🏆 Placar Atual 🏆</b>\n"
            f"🥇 <b>Vitórias de Primeira</b> {self.win_first_try}\n"
            f"🥈 <b>Vitórias Gale 1:</b> {self.win_gale1}\n"
            f"💚 <b>Total de Vitórias:</b> {self.win_results}\n"
            f"💔 <b>Loss:</b> {self.loss_results}\n"
            f"🎯 <b>Assertividade:</b> {self.win_hate}\n"
            f"♻️ <b>Sequência Máxima:</b> {self.max_streak}\n"
        )
        for g_id in self.chat_ids:
            self.safe_send_message(g_id, placar, parse_mode="html")

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

    # =========== ENVIO DE SINAL (palpite confirmado) ===========
    def send_sinal(self, finalnum):
        self.analisar = False
        self.total_palpites += 1

        print(f"💥 Palpite Confirmado para {self.alvo}x após {finalnum}x 💥")

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

        # Não Mostra mais o placar logo após enviar o palpite pois removi a linha send results abaixo

    # ===================== MARTINGALE =====================
    def martingale(self, resultado, finalnum):
        # ---------- WIN ----------
        if resultado == "WIN":
            self.win_results += 1
            self.max_hate += 1
            self.win_streak += 1
            self.max_streak = max(self.max_streak, self.win_streak)

            # Stickers & mensagens
            if self.count == 0:
                self.win_first_try += 1
                for g_id in self.chat_ids:
                    self.safe_send_sticker(g_id, self.STK_WIN_SEM_GALE)
                    self.safe_send_message(g_id, "<b>Win Sem Gale ✅</b>", parse_mode="html")
            elif self.count == 1:
                self.win_gale1 += 1
                for g_id in self.chat_ids:
                    self.safe_send_sticker(g_id, self.STK_WIN_GALE)
                    self.safe_send_message(g_id, "<b>Win Gale 1 ✅</b>", parse_mode="html")
            elif self.count == 2:
                self.win_gale2 += 1
                for g_id in self.chat_ids:
                    self.safe_send_sticker(g_id, self.STK_WIN_GALE)
                    self.safe_send_message(g_id, "<b>Win Gale 2 ✅</b>", parse_mode="html")

            for g_id in self.chat_ids:
                self.safe_send_message(
                    g_id, f"<b>Vitória em {finalnum}x ✅</b>", parse_mode="html"
                )

        # ---------- LOSS ----------
        else:  # "LOSS"
            self.count += 1
            if self.count > self.gales:
                self.loss_results += 1
                self.win_streak = 0
                self.max_hate = 0
                for g_id in self.chat_ids:
                    self.safe_send_sticker(g_id, self.STK_LOSS)
                    self.safe_send_message(g_id, "<b>LOSS ❌</b>", parse_mode="html")
            else:
                # Vai para o próximo gale
                self.alert_gale()
                return  # não reseta analisar nem envia placar ainda

        # ---------- ENCERRA CICLO ----------
        self.count = 0
        self.analisar = True
        self.delete()   # limpa alertas pendentes
        self.results()  # placar em tempo real
        self.restart()  # verifica se mudou o dia

    # ===================== CHECAGEM DE RESULTADO =====================
    def check_results(self, results):
        # Se bateu alvo → WIN, senão LOSS
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
        # Se já existe palpite em jogo, apenas verifica WIN / LOSS
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

# ---------- E2 ----------
        if (
            len(results) >= 11
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
        ):
            print("SINAL ENCONTRADO! E2")
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
        
         # ---------- E4 ----------
        if (
            len(results) >= 11
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] >= 2.0
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] >= 2.0
            and results[10] <= 1.99
        ):
            print("SINAL ENCONTRADO! E4")
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
        
        # ---------- E10 ----------
        if (
            len(results) >= 10
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] <= 1.99
            and results[7] >= 2.0
            and results[8] <= 1.99
            and results[9] <= 1.99
        ):
            print("SINAL ENCONTRADO! E10")
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
        
        # ---------- E15 ----------
        if (
            len(results) >= 13
            and results[0] <= 1.99
            and results[1] <= 1.99
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] >= 2.0
            and results[6] <= 1.99
            and results[7] <= 1.99
            and results[8] <= 1.99
            and results[9] >= 2.0
            and results[10] <= 1.99
            and results[11] <= 1.99
            and results[12] <= 1.99
        ):
            print("SINAL ENCONTRADO! E15")
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
        
        # ---------- E22 ----------
        if (
            len(results) >= 10
            and results[0] >= 2.0
            and results[1] <= 1.99
            and results[2] <= 1.99
            and results[3] <= 1.99
            and results[4] >= 2.0
            and results[5] <= 1.99
            and results[6] >= 2.0
            and results[7] >= 2.0
            and results[8] <= 1.99
            and results[9] <= 1.99
        ):
            print("SINAL ENCONTRADO! E22")
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
        
        # ---------- E26 ----------
        if (
            len(results) >= 12
            and results[0] <= 1.99
            and results[1] >= 2.0
            and results[2] <= 1.99
            and results[3] >= 2.0
            and results[4] <= 1.99
            and results[5] <= 1.99
            and results[6] >= 2.0
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] <= 1.99
            and results[10] >= 2.0
            and results[11] >= 2.0
        ):
            print("SINAL ENCONTRADO! E26")
            self.alvo = 1.99
            self.send_sinal(results[0])
            return
        
        # ---------- E27 ----------
        if (
            len(results) >= 12
            and results[0] <= 1.99
            and results[1] >= 2.0
            and results[2] >= 2.0
            and results[3] <= 1.99
            and results[4] <= 1.99
            and results[5] >= 2.0
            and results[6] >= 2.0
            and results[7] <= 1.99
            and results[8] >= 2.0
            and results[9] >= 2.0
            and results[10] <= 1.99
            and results[11] >= 2.0
        ):
            print("SINAL ENCONTRADO! E27")
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

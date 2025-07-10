from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
import json
import psycopg2
from datetime import datetime, timedelta
from sqlalchemy import desc, asc
app = Flask(__name__)
import pandas as pd
from flask import send_file
from sqlalchemy import or_
from io import BytesIO
import requests
import xml.etree.ElementTree as ET

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://webhook_bling_user:9yH7z6LmIl9FBVTjlfmCE8LmdsRTlNjV@dpg-d1hf3iqdbo4c73dbgdqg-a.oregon-postgres.render.com/webhook_bling'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def extrair_itens_xml(xml_url):
    try:
        response = requests.get("https://www.bling.com.br/relatorios/nfe.xml.php?chaveAcesso=" + xml_url)
        response.raise_for_status()

        # Define o namespace da NFe
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

        # Faz parsing do XML
        root = ET.fromstring(response.content)

        itens = []

        # Percorre os elementos <det> com namespace
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            if prod is not None:
                cProd = prod.findtext('nfe:cProd', default='', namespaces=ns)
                qCom = prod.findtext('nfe:qCom', default='0', namespaces=ns)

                itens.append({
                    'codigo_produto': cProd.strip(),
                    'quantidade': float(qCom.replace(',', '.'))
                })

        return itens

    except Exception as e:
        print("Erro ao processar XML:", e)
        return []
    
class Pedido(db.Model):
    __tablename__ = 'pedidos'

    hora = db.Column(db.DateTime, nullable=False)  # Nova coluna com data/hora atual
    id = db.Column(db.BigInteger, primary_key=True)  # ID da nota fiscal
    status = db.Column(db.String(50), nullable=False)
    idloja = db.Column(db.String(50), nullable=False)
    chaveacesso = db.Column(db.String(100), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    numnfe = db.Column(db.String(50), nullable=False)

class ItemPedido(db.Model):
    __tablename__ = 'itens_pedido'

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.BigInteger, db.ForeignKey('pedidos.id'), nullable=False)
    codigo_produto = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Float, nullable=False)

    pedido = db.relationship('Pedido', backref=db.backref('itens', cascade="all, delete-orphan"))

@app.route('/limpar_pedidos')
def limpar_pedidos():
    try:
        num = db.session.query(Pedido).delete()  # apaga todas as linhas
        db.session.commit()
        return f"{num} pedidos deletados com sucesso!"
    except Exception as e:
        db.session.rollback()
        return f"Erro ao deletar pedidos: {str(e)}"

def get_nome_loja_por_id(id_loja):
    lojas = {
        "205389154": "AmazonFBA",
        "205074078": "Angeloni",
        "203614915": "B2W",
        "203630666": "Carrefour",
        "204860113": "Casa&Video",
        "204426107": "FastShop",
        "203742895": "Kabum",
        "205146734": "LLLoyalty",
        "204860094": "LeBiscuit",
        "203630664": "Mercado Livre",
        "203630663": "Magazine Luiza",
        "205024699" : "Netshoes",
        "204206885" :"NextShop",
        "204503878": "Olist",
        "204817223" :"Privalia",
        "205211252" : "Renner",
        "204621267" : "RiHappy",
        "204556538" : "Shein",
        "203954967": "Shopee",
        "205113356": "ShoppingBB",
        "204484960 ":"Livelo",
        "205408211" :"TikTok",
        "203630665":"ViaVarejo",
        "205408232":"VinkLo",
        "205055610":"Zema",
        "205103397":"Zoom",
        "203861198" : "Candide",
        "205126496": "Funko"
    }
    return lojas.get(id_loja, "Loja desconhecida")


@app.route("/webhook", methods=["POST"])
def receber_webhook():
    try:
        raw_body = request.get_data(as_text=True)
        print("Corpo bruto recebido:", raw_body)

        if raw_body.startswith("data="):
            raw_body = raw_body[5:]

        data = json.loads(raw_body)
        print("JSON limpo:", data)

        if not data:
            return jsonify({'erro': 'Nenhum dado recebido'}), 400

        notas = data.get('retorno', {}).get('notasfiscais', [])

        for item in notas:
            nota = item.get('notafiscal', {})

            if nota.get('situacao') in ['Autorizada', 'Enviada - Aguardando protocolo'] and nota.get('loja') != "203789189" and nota.get('tipo') == "S":
                status = 'Autorizada'

                novo_pedido = Pedido(
                    hora=datetime.now() - timedelta(hours=3),
                    id=int(nota.get('id')),
                    status=status,
                    idloja=get_nome_loja_por_id(nota.get('loja')),
                    chaveacesso=nota.get('chaveAcesso'),
                    nome=nota.get('cliente', {}).get('nome'),
                    numnfe=nota.get('numero')
                )

                existente = Pedido.query.get(novo_pedido.id)
                if not existente:
                    db.session.add(novo_pedido)
                    db.session.commit()
                    print(f"Salvo: {novo_pedido.id}")

                    xml_url = nota.get('chaveAcesso')
                    if xml_url:
                        itens_xml  = extrair_itens_xml(xml_url)
                        print(f"Itens extraídos para pedido {novo_pedido.id}: {itens_xml}")
                        for item_xml in itens_xml:
                            novo_item = ItemPedido(
                                pedido_id=novo_pedido.id,
                                codigo_produto=item_xml['codigo_produto'],
                                quantidade=item_xml['quantidade']
                            )
                            db.session.add(novo_item)

                        db.session.commit()

                        db.session.commit()

                else:
                    print(f"Já existe: {novo_pedido.id}")

            elif nota.get('situacao') == "Cancelada":
                chave = nota.get('chaveAcesso')
                pedidos = Pedido.query.filter_by(chaveacesso=chave).all()

                if not pedidos:
                    print(f"Nenhum pedido encontrado para a chave {chave}")
                    continue

                for pedido in pedidos:
                    pedido.status = "Cancelado"

                db.session.commit()
                print(f"Pedidos com chave {chave} atualizados como Cancelado")

        return jsonify({'status': 'Processamento concluído'}), 200

    except Exception as e:
        print('Erro ao processar webhook:', e)
        return jsonify({'erro': str(e)}), 500


@app.route('/pedidos')
def listar_pedidos():
    pedidos = Pedido.query.filter(
    or_(
        Pedido.status == "Autorizada",
        Pedido.status == "Buffered"
    )
).order_by(asc(Pedido.status)).all()
    total_pedidos = len(pedidos)
    return render_template('pedidos.html', pedidos=pedidos, total_pedidos=total_pedidos)
  

@app.route('/bipar', methods=['POST'])
def bipar_pedido():
    data = request.get_json()
    chave = data.get('chave')

    if not chave:
        return jsonify({'erro': 'Chave de acesso não fornecida'}), 400

    pedidos = Pedido.query.filter_by(chaveacesso=chave).all()

    if not pedidos:
        return jsonify({'mensagem': 'Nenhum pedido encontrado com essa chave'}), 404

    # Verifica se algum pedido já está como Bipado
    if any(p.status == "Bipado" for p in pedidos):
        return jsonify({'erro': 'Pedido já está com status Bipado'}), 400

    # Atualiza os pedidos
    for pedido in pedidos:
        pedido.status = "Bipado"

    db.session.commit()

    # Atualiza a tabela com pedidos autorizados
    pedidos_atualizados = Pedido.query.filter(
    or_(
        Pedido.status == "Autorizada",
        Pedido.status == "Buffered"
    )
    ).order_by(asc(Pedido.status)).all()
    total_pedidos = len(pedidos_atualizados)
    pedidos_data = [{
        'id': p.id,
        'hora': p.hora.strftime('%d/%m/%Y %H:%M'),
        'status': p.status,
        'idloja': p.idloja,
        'chaveacesso': p.chaveacesso,
        'nome': p.nome,
        'numnfe': p.numnfe
    } for p in pedidos_atualizados]

    return jsonify({'mensagem': 'Pedido(s) bipado(s) com sucesso', 'pedidos': pedidos_data, 'total_pedidos': total_pedidos}), 200


@app.route('/relatorio', methods=['GET', 'POST'])
def relatorio():
    marketplaces = db.session.query(Pedido.idloja).distinct().all()
    status_list = db.session.query(Pedido.status).distinct().all()

    marketplaces = [m[0] for m in marketplaces]
    status_list = [s[0] for s in status_list]

    relatorio_detalhado = []

    if request.method == 'POST':
        selected_marketplace = request.form.get('marketplace')
        selected_status = request.form.get('status')
        data_inicial = request.form.get('data_inicial')
        data_final = request.form.get('data_final')

        query = Pedido.query

        if selected_marketplace:
            query = query.filter_by(idloja=selected_marketplace)

        if selected_status:
            query = query.filter_by(status=selected_status)

        if data_inicial:
            try:
                dt_ini = datetime.strptime(data_inicial, "%Y-%m-%d")
                query = query.filter(Pedido.hora >= dt_ini)
            except ValueError:
                pass

        if data_final:
            try:
                dt_fim = datetime.strptime(data_final, "%Y-%m-%d")
                dt_fim = dt_fim.replace(hour=23, minute=59, second=59)
                query = query.filter(Pedido.hora <= dt_fim)
            except ValueError:
                pass

        pedidos = query.order_by(Pedido.hora.desc()).all()

        for pedido in pedidos:
            for item in pedido.itens:
                relatorio_detalhado.append({
                    'nfe': pedido.numnfe,
                    'marketplace': pedido.idloja,
                    'sku': item.codigo_produto,
                    'quantidade': item.quantidade
                })

    return render_template(
        'relatorio.html',
        marketplaces=marketplaces,
        status_list=status_list,
        pedidos=relatorio_detalhado
    )

@app.route('/buffer_status', methods=['POST'])
def buffer_status():
    data = request.get_json()
    pedido_id = data.get('id')

    if not pedido_id:
        return jsonify({'erro': 'ID do pedido não fornecido'}), 400

    pedido = Pedido.query.get(pedido_id)

    if not pedido:
        return jsonify({'erro': 'Pedido não encontrado'}), 404

    if pedido.status != "Autorizada":
        return jsonify({'erro': f'O pedido está com status "{pedido.status}", não pode ser alterado.'}), 400

    pedido.status = "Buffered"
    db.session.commit()

    return jsonify({'mensagem': f'Pedido {pedido_id} atualizado para Buffered com sucesso.'}), 200


@app.route('/dashboard')
def dashboard():
    total = Pedido.query.count()
    cancelados = Pedido.query.filter_by(status="Cancelado").count()
    autorizados = Pedido.query.filter_by(status="Autorizada").count()
    bipados = Pedido.query.filter_by(status="Bipado").count()
    
    return render_template('dashboard.html', total=total, cancelados=cancelados, autorizados=autorizados, bipados=bipados)


@app.route('/download_relatorio', methods=['POST'])
def download_relatorio():
    selected_marketplace = request.form.get('marketplace')
    selected_status = request.form.get('status')
    data_inicial = request.form.get('data_inicial')
    data_final = request.form.get('data_final')

    query = Pedido.query

    if selected_marketplace:
        query = query.filter_by(idloja=selected_marketplace)

    if selected_status:
        query = query.filter_by(status=selected_status)

    if data_inicial:
        try:
            dt_ini = datetime.strptime(data_inicial, "%Y-%m-%d")
            query = query.filter(Pedido.hora >= dt_ini)
        except ValueError:
            pass

    if data_final:
        try:
            dt_fim = datetime.strptime(data_final, "%Y-%m-%d")
            dt_fim = dt_fim.replace(hour=23, minute=59, second=59)
            query = query.filter(Pedido.hora <= dt_fim)
        except ValueError:
            pass

    pedidos = query.all()

    # Convertendo para DataFrame
    df = pd.DataFrame([{
        "Data": p.hora.strftime("%d/%m/%Y %H:%M"),
        "ID": p.id,
        "Status": p.status,
        "Loja": p.idloja,
        "Chave de Acesso": p.chaveacesso,
        "Nome": p.nome,
        "Num. NFe": p.numnfe
    } for p in pedidos])

    # Criar Excel em memória
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')

    output.seek(0)

    return send_file(
        output,
        download_name='relatorio_pedidos.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


if __name__ == '__main__':
    app.run(debug=True)
    #print(extrair_itens_xml("35250762434436001703550020003131411225750547"))

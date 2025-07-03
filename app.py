from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
import json
import psycopg2
from datetime import datetime
from sqlalchemy import desc
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://webhook_bling_user:9yH7z6LmIl9FBVTjlfmCE8LmdsRTlNjV@dpg-d1hf3iqdbo4c73dbgdqg-a.oregon-postgres.render.com/webhook_bling'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Pedido(db.Model):
    __tablename__ = 'pedidos'

    hora = db.Column(db.DateTime, default=datetime.now, nullable=False)  # Nova coluna com data/hora atual
    id = db.Column(db.BigInteger, primary_key=True)  # ID da nota fiscal
    status = db.Column(db.String(50), nullable=False)
    idloja = db.Column(db.String(50), nullable=False)
    chaveacesso = db.Column(db.String(100), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    numnfe = db.Column(db.String(50), nullable=False)


@app.route('/webhook', methods=['POST'])
def receber_webhook():
    try:
        raw_body = request.get_data(as_text=True)
        print("Corpo bruto recebido:", raw_body)

        # Se começar com "data=", remove isso
        if raw_body.startswith("data="):
            raw_body = raw_body[5:]

        # Decodifica o conteúdo JSON (que estava como string dentro de 'data=')
        data = json.loads(raw_body)
        print("JSON limpo:", data)
        if not data:
            return jsonify({'erro': 'Nenhum dado recebido'}), 400

        print('DATA DECODIFICADO:', data)

        notas = data.get('retorno', {}).get('notasfiscais', [])

        for item in notas:
            nota = item.get('notafiscal', {})
            if nota.get('situacao') == 'Autorizada':
                novo_pedido = Pedido(
                    hora=datetime.datetime.now(),
                    id=int(nota.get('id')),
                    status=nota.get('situacao'),
                    idloja=nota.get('loja'),
                    chaveacesso=nota.get('chaveAcesso'),
                    nome=nota.get('cliente', {}).get('nome'),
                    numnfe=nota.get('numero')
                )

                existente = Pedido.query.get(novo_pedido.id)
                if not existente:
                    db.session.add(novo_pedido)
                    db.session.commit()
                    print(f"Salvo: {novo_pedido.id}")
                else:
                    print(f"Já existe: {novo_pedido.id}")

        return jsonify({'status': 'sucesso'}), 200

    except Exception as e:
        print('Erro ao processar webhook:', e)
        return jsonify({'erro': str(e)}), 500


@app.route('/pedidos')
def listar_pedidos():
    pedidos = Pedido.query.filter_by(status="Autorizada").all()
    return render_template('pedidos.html', pedidos=pedidos)

@app.route('/bipar', methods=['POST'])
def bipar_pedido():
    data = request.get_json()
    chave = data.get('chave')

    if not chave:
        return jsonify({'erro': 'Chave de acesso não fornecida'}), 400

    pedidos = Pedido.query.filter_by(chaveacesso=chave).all()

    if not pedidos:
        return jsonify({'mensagem': 'Nenhum pedido encontrado com essa chave'}), 404

    for pedido in pedidos:
        pedido.status = "Bipado"

    db.session.commit()

    # Buscar todos os pedidos novamente para atualizar a tabela
    pedidos_atualizados = Pedido.query.order_by(desc(Pedido.hora)).all()

    pedidos_data = [{
        'id': p.id,
        'hora': p.hora.strftime('%d/%m/%Y %H:%M'),
        'status': p.status,
        'idloja': p.idloja,
        'chaveacesso': p.chaveacesso,
        'nome': p.nome,
        'numnfe': p.numnfe
    } for p in pedidos_atualizados]

    return jsonify({'mensagem': 'Pedido(s) bipado(s) com sucesso', 'pedidos': pedidos_data}), 200
if __name__ == '__main__':
    app.run(debug=True)

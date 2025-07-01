from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
import json
import psycopg2

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://webhook_bling_user:9yH7z6LmIl9FBVTjlfmCE8LmdsRTlNjV@dpg-d1hf3iqdbo4c73dbgdqg-a.oregon-postgres.render.com/webhook_bling'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Pedido(db.Model):
    __tablename__ = 'pedidos'

    id = db.Column(db.BigInteger, primary_key=True)  # ID da nota fiscal
    status = db.Column(db.String(50), nullable=False)
    idloja = db.Column(db.String(50), nullable=False)
    chaveacesso = db.Column(db.String(100), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    numnfe = db.Column(db.String(50), nullable=False)


@app.route('/webhook', methods=['POST'])
def receber_webhook():
    try:
        print("Headers:", dict(request.headers))
        print("Body:", request.data.decode('utf-8'))
        print("JSON:", request.get_json())  # cuidado: pode dar erro se o JSON for inválido
        raw_data = request.form.get('data')  # ou request.values.get('data')
        print(raw_data)
        if not raw_data:
            return jsonify({'erro': 'Nenhum dado recebido'}), 400

        data = json.loads(raw_data)  # Agora sim é um dicionário Python
        print('DATA DECODIFICADO:', data)

        notas = data.get('retorno', {}).get('notasfiscais', [])

        for item in notas:
            nota = item.get('notafiscal', {})
            if nota.get('situacao') == 'Autorizada':
                novo_pedido = Pedido(
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
    pedidos = Pedido.query.all()
    print(pedidos)
    return render_template('pedidos.html', pedidos=pedidos)


if __name__ == '__main__':
    app.run(debug=True)

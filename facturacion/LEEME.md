# Movimientos de las apps uruguayas → planilla (para la facturación)

Objetivo: que cada plata que entra en **MiDinero, Prex, OCA Blue, Itaú y Mercado Pago/Libre** llegue sola
a `Facturas UY` (Registro BEXO), en vez de copiarla a mano.

## Por qué por las notificaciones

Cada una de esas apps ya te avisa en el teléfono cuando entra plata. Leer ese aviso:

- no necesita entrar a ninguna app, ni claves, ni huella: es lo mismo que mirar la cortina de notificaciones;
- sirve igual para las 5 apps (un solo script, no cinco integraciones);
- es **solo lectura**: no puede aprobar ni mover nada.

Lo que no cubre: lo que pasó antes de empezar (eso se trae una vez con el export de cada app) y los
avisos que la app no manda (por eso, en cada app, dejá prendidas las notificaciones de "dinero recibido").

## Paso 1 (ahora): ver cómo escribe cada app

Cada comando en su propio bloque: copiá, pegá en Termux, Enter, y pasá al siguiente.

1. En Android: Ajustes → Notificaciones → **Acceso a notificaciones** (a veces "Notificaciones de dispositivos
   y apps") → **Termux:API** → activar. Sin esto el teléfono no le deja leer los avisos.

2. Traer la última versión de los scripts:

```
git -C ~/bexo-scripts pull
```

3. Ver los avisos que hay ahora de esas apps (no manda nada a ningún lado):

```
python ~/bexo-scripts/facturacion/notifs_apps.py --ver
```

Muestra cada aviso con la app, el título, el texto y el monto que entendió. Si una app no aparece aunque
tenga un aviso en la cortina, este muestra los de todas las apps para encontrar su nombre:

```
python ~/bexo-scripts/facturacion/notifs_apps.py --todas
```

4. Dejarlo anotando solo (cada 60 s guarda los avisos nuevos en `~/movimientos_apps.csv`):

```
chmod +x ~/bexo-scripts/telefono/avisos.sh
```

```
sh ~/bexo-scripts/telefono/avisos.sh
```

5. Que se vuelva a arrancar solo cada 15 minutos si Android lo cierra (trabajo 5 de Termux):

```
termux-job-scheduler --job-id 5 --script ~/bexo-scripts/telefono/avisos.sh --period-ms 900000 --persisted true
```

Para ver lo que fue anotando:

```
tail -20 ~/avisos.log
```

## Paso 2 (siguiente)

Con unos días de avisos reales se ajusta cómo leer fecha, monto y nombre de cada app, y se mandan a la
planilla por el webhook de siempre, a una pestaña nueva (no se toca lo que cargaste a mano en `Facturas UY`).

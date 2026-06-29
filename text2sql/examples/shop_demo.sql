-- ============================================================================
--  shop_demo — a small e-commerce schema for testing text2sql.
--  Load with:  psql -d shop_demo -f examples/shop_demo.sql
--  Order/payment dates are anchored to CURRENT_DATE so "this month" queries
--  always return data regardless of when you run it.
-- ============================================================================

DROP TABLE IF EXISTS order_items, payments, orders, products, customers CASCADE;

-- ---------------------------------------------------------------------------
CREATE TABLE customers (
    id          serial PRIMARY KEY,
    name        text        NOT NULL,
    email       text        NOT NULL UNIQUE,
    country     text        NOT NULL DEFAULT 'VN',
    created_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE  customers          IS 'People who place orders in the shop.';
COMMENT ON COLUMN customers.country  IS 'ISO country code, e.g. VN, US, JP.';

CREATE TABLE products (
    id        serial PRIMARY KEY,
    name      text          NOT NULL,
    category  text          NOT NULL,
    price     numeric(10,2) NOT NULL,
    stock     integer       NOT NULL DEFAULT 0
);
COMMENT ON TABLE  products       IS 'Catalogue of items for sale.';
COMMENT ON COLUMN products.price IS 'Unit price in USD.';

CREATE TABLE orders (
    id           serial PRIMARY KEY,
    customer_id  integer     NOT NULL REFERENCES customers(id),
    status       text        NOT NULL DEFAULT 'paid',  -- paid | pending | cancelled
    created_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE  orders        IS 'A purchase placed by a customer; line items live in order_items.';
COMMENT ON COLUMN orders.status IS 'One of: paid, pending, cancelled.';
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_created  ON orders(created_at);

CREATE TABLE order_items (
    id          serial PRIMARY KEY,
    order_id    integer       NOT NULL REFERENCES orders(id),
    product_id  integer       NOT NULL REFERENCES products(id),
    quantity    integer       NOT NULL CHECK (quantity > 0),
    unit_price  numeric(10,2) NOT NULL
);
COMMENT ON TABLE order_items IS 'Individual product lines within an order.';

CREATE TABLE payments (
    id         serial PRIMARY KEY,
    order_id   integer       NOT NULL REFERENCES orders(id),
    amount     numeric(10,2) NOT NULL,
    method     text          NOT NULL,   -- card | cash | transfer
    paid_at    timestamptz   NOT NULL DEFAULT now()
);
COMMENT ON TABLE payments IS 'Money received against an order.';

-- ---------------------------------------------------------------------------
-- Seed data
-- ---------------------------------------------------------------------------
INSERT INTO customers (name, email, country) VALUES
    ('Alice Nguyen',  'alice@example.com',  'VN'),
    ('Bao Tran',      'bao@example.com',    'VN'),
    ('Charlie Pham',  'charlie@example.com','US'),
    ('Diana Le',      'diana@example.com',  'JP'),
    ('Erik Vo',       'erik@example.com',   'VN');

INSERT INTO products (name, category, price, stock) VALUES
    ('Mechanical Keyboard', 'Electronics', 89.00,  120),
    ('USB-C Cable',         'Electronics',  9.50,  500),
    ('Coffee Mug',          'Home',        12.00,  300),
    ('Notebook',            'Stationery',   4.50,  800),
    ('Standing Desk',       'Furniture',  299.00,   25),
    ('Desk Lamp',           'Home',        34.90,   90);

-- Orders: most are this month; a few in prior months for contrast.
-- Alice gets the most orders THIS month (4), Bao next (2), others 1.
INSERT INTO orders (customer_id, status, created_at) VALUES
    (1, 'paid',      date_trunc('month', now()) + interval '2 days'),
    (1, 'paid',      date_trunc('month', now()) + interval '5 days'),
    (1, 'paid',      date_trunc('month', now()) + interval '9 days'),
    (1, 'pending',   date_trunc('month', now()) + interval '12 days'),
    (2, 'paid',      date_trunc('month', now()) + interval '3 days'),
    (2, 'paid',      date_trunc('month', now()) + interval '7 days'),
    (3, 'paid',      date_trunc('month', now()) + interval '6 days'),
    (4, 'cancelled', date_trunc('month', now()) + interval '4 days'),
    (5, 'paid',      now() - interval '45 days'),
    (3, 'paid',      now() - interval '60 days');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 1,  89.00), (1, 2, 2,   9.50),
    (2, 3, 4,  12.00),
    (3, 5, 1, 299.00), (3, 6, 1,  34.90),
    (4, 4, 10,  4.50),
    (5, 1, 1,  89.00),
    (6, 2, 3,   9.50),
    (7, 6, 2,  34.90),
    (8, 3, 1,  12.00),
    (9, 5, 1, 299.00),
    (10, 1, 2, 89.00);

INSERT INTO payments (order_id, amount, method) VALUES
    (1, 108.00, 'card'),     (2, 48.00, 'cash'),    (3, 333.90, 'transfer'),
    (5,  89.00, 'card'),     (6, 28.50, 'card'),    (7,  69.80, 'transfer'),
    (9, 299.00, 'card'),     (10, 178.00, 'card');

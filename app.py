import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, lookups

# updated January 19, 2022
# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
#app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False # when close browser, cookies go away
app.config["SESSION_TYPE"] = "filesystem"
Session(app) # we tell our app to support sessions

uri = os.getenv("DATABASE_URL")  # or other relevant config var
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
# rest of connection code using the connection string `uri`

# Configure CS50 Library to use SQLite database
#db = SQL("sqlite:///finance.db")
db = SQL(uri)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/update")
@login_required
def update():
    id_user = session["user_id"]

    stocks = db.execute("SELECT symbol,name,price,total, SUM(shares) FROM symbol WHERE user_id=? GROUP BY name,symbol,name,price,total;", id_user)
    balances = db.execute("SELECT cash FROM users WHERE id=? ;", id_user)

    # User account balance
    for balance in balances:
        cash = balance["cash"]

    # Updating prices on stocks
    total_stock = 0.00
    for stock in stocks:
        symbol = stock["symbol"]
        data = lookup(symbol)

        # Price for one share
        price = data['price']
        stock["price"] = price  # update current price

        # Stock Total
        total_shares = stock["SUM(shares)"]
        cost = price*total_shares
        stock["total"] = cost  # update total price
        total_stock = cost + total_stock

    # Total sum of new prices of stocks + balance in account
    total_balance = cash + total_stock

    return render_template("update.html", stocks=stocks, cash=cash, total_balance=total_balance)

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    id_user = session["user_id"]
    
    # Retrieving stocks from user
    stocks = db.execute("SELECT symbol,name,SUM(shares) AS shares FROM symbol WHERE user_id=? GROUP BY symbol,name;", id_user)
    
    dcash = db.execute("SELECT cash FROM users WHERE id=?", id_user)
    cash = dcash[0]

    dict_stock = {'symbol':'', 'name':'', 'shares':0, 'price':0.00, 'total':0.00}
    l_stock = []

    total_stock = 0.00

    for stock in stocks:
        symbol = stock["symbol"]
        data = lookup(symbol)

        # Price for one share
        price = data["price"]
        dict_stock["price"] = price  # update current price

        # Stock Total
        sumtotal = stock['shares']
        cost = price*(sumtotal)
        dict_stock["total"] = cost  # update total price
        
        # Keeping a tally sum of all stocks
        total_stock = cost + total_stock
        
        dict_stock['symbol'] = stock['symbol']
        dict_stock['name'] = stock['name']
        dict_stock['shares'] = stock['shares']
        
        dict_copy = dict_stock.copy()
        l_stock.append(dict_copy)

    # Total sum of new prices of stocks + balance in account
    total_balance = cash['cash'] + total_stock

    return render_template("index.html", l_stock=l_stock, cash=cash, total_balance=total_balance)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)
        if not request.form.get("shares"):
            return apology("must fill out # of shares", 400)

        symbol = lookup(request.form.get("symbol"))

        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("shares must be a positive integer", 400)

        if symbol is None:
            return apology("must provide valid symbol", 400)
        else:
            id_user = session["user_id"]

            rows = db.execute("SELECT cash FROM users WHERE id=?", id_user)
            balance = float(rows[0]["cash"])
            price = float(symbol['price'])
            name = symbol['name']
            symbol = symbol['symbol']

            cost = float(shares * price)

            if (balance > cost):
                balance = balance - cost
                db.execute("UPDATE users SET cash=? WHERE id=?", balance, id_user)
                db.execute("INSERT INTO symbol(user_id, symbol, name, shares, price, total) VALUES(?,?,?,?,?,?)", id_user, symbol, name, shares, price, cost)
                flash("Bought Successfully!")
                return redirect("/")
            else:
                return apology("Not enough funds :( ", 400)

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    id_user = session["user_id"]

    transactions = db.execute("SELECT * FROM symbol WHERE user_id=?", id_user)

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    flash("Logged Out Successfully!")
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        symbol = lookup(request.form.get("symbol"))

        if symbol is None:
            return apology("must provide valid symbol", 400)
        else:
            return render_template("quoted.html", symbol=symbol)

    else:
        return render_template("quote.html")


@app.route("/searchquote")
def index2():
    return render_template("index2.html")

@app.route("/search")
def search():
    q = request.args.get("q")
    if q:
        #shows = db.execute("SELECT DISTINCT name FROM symbol WHERE name LIKE ? LIMIT 50", "%" + q + "%")
        shows = lookups(q)
        print(shows)
    else:
        shows = []
    return jsonify(shows)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

         # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

         # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username is unique
        if len(rows) == 1:
            return apology("username already taken!", 400)


        # Registering user in database
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure passwords match
        if password != confirmation:
            return apology("passwords must match!", 400)

        password = generate_password_hash(password)

        db.execute("INSERT INTO users(username, hash) VALUES (?, ?)", username, password)
        
        flash("Registered Successfully!")

        return render_template("login.html")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    id_user = session["user_id"]
    stocks = db.execute("SELECT symbol,name,SUM(shares) AS shares FROM symbol WHERE user_id=? GROUP BY symbol,name;", id_user)

    if request.method == "POST":
        # inserting symbol
        symbol = request.form.get("symbol")
        # checks to see if user left symbol blank
        if not symbol:
            return apology("Must fill out symbol field", 400)
        # gets users amount they want to sell and handles checking cases
        selling_shares = int(request.form.get("shares"))
        if not selling_shares:
            return apology("Insert # of shares you'd like to sell")

        sum_shares = db.execute("SELECT symbol,name,SUM(shares) AS shares FROM symbol WHERE user_id=? AND symbol=? GROUP BY symbol,name;", id_user,symbol)
        
        if selling_shares > sum_shares[0]["shares"]:
            return apology("You don't own that many shares")

        data = lookup(symbol)

        # Price for one share
        share_price = data['price']

        # Name of share
        name = data['name']

        # Total price for selling shares
        selling_total = share_price*selling_shares

        rows = db.execute("SELECT cash FROM users WHERE id=?", id_user)
        balance = float(rows[0]["cash"])

        balance = balance + selling_total
        db.execute("UPDATE users SET cash=? WHERE id=?", balance, id_user)
        db.execute("INSERT INTO symbol(user_id, symbol, name, shares, price, total) VALUES(?,?,?,?,?,?)", id_user, symbol, name, -selling_shares, share_price, -selling_total)
        flash("Sold Successfully!")

        return redirect("/")
    else:
        return render_template("sell.html", stocks=stocks)
#fixed not working
@app.route("/account", methods=["GET", "POST"])
@login_required
def changepswd():
    if request.method == "POST":
        id_user = session["user_id"]

        # Changing password
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure passwords match
        if password != confirmation:
            return apology("passwords must match!", 400)

        id_user = session["user_id"]
        password = generate_password_hash(password)

        db.execute("UPDATE users SET hash =? WHERE id=?", password, id_user)
        flash("Password Successfully Changed!")
        return redirect("/")

    else:
        return render_template("account.html")

@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
    if request.method == "POST":
        id_user = session["user_id"]

        # Adding cash
        cash = float(request.form.get("cash"))

        rows = db.execute("SELECT cash FROM users WHERE id=?", id_user)
        balance = float(rows[0]["cash"])

        balance = balance + cash


        db.execute("UPDATE users SET cash=? WHERE id=?", balance, id_user)

        flash("Cash Added Successfully!")

        return redirect("/")

    else:
        return render_template("account.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

---
layout: default
title: Transactions | Boston Red Sox moves & trades
description: An auto-updating log of recent Red Sox player transactions.
permalink: /transactions/
canonical_url: https://redsoxdata.bot/transactions/
header:
  og_image: /assets/images/meta_card.png
twitter:
  card: summary_large_image
---

<div class="container">
  <div class="minimal-header">
    <h1 class="minimal-headline">Recent transactions</h1>
    <p class="minimal-subhead">A log of the team's last 100 player moves, according to <a href="https://www.mlb.com/redsox/roster/transactions">Major League Baseball</a>: </p>
  </div>

  {% assign transactions = site.data.roster.redsox_transactions_current %}
  {% assign players_roster = site.data.roster.redsox_roster_current %}

  <div class="transactions-grid">
    {% for transaction in transactions %}
      <div class="stat-card transaction-card">
        <div class="transaction-date">{{ transaction.date | date: "%B %-d, %Y" }}</div>

        {% if transaction.players %}
          <div class="transaction-players-container">
            {% for player_name in transaction.players %}
              <div class="player-profile-transaction">
                <div class="player-name-transaction">{{ player_name }}</div>
                <img src="{{ '/assets/images/placeholder-avatar.png' | absolute_url }}" alt="{{ player_name }}" title="{{ player_name }}" class="player-avatar-transaction" />
              </div>
            {% endfor %}
          </div>
        {% endif %}

        <div class="transaction-description">
          {{ transaction.transaction }}
        </div>
      </div>
    {% endfor %}
  </div>
</div> 
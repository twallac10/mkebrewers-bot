---
layout: default
title: Transactions | Milwaukee Brewers moves & trades
description: An auto-updating log of recent Brewers player transactions.
permalink: /transactions/
canonical_url: https://mkebrewers.bot/transactions/
header:
  og_image: /assets/images/meta_card.png
twitter:
  card: summary_large_image
---

<div class="container">
  <div class="minimal-header">
    <h1 class="minimal-headline">Recent transactions</h1>
    <p class="minimal-subhead">A log of the team's last 100 player moves, according to <a href="https://www.mlb.com/brewers/roster/transactions">Major League Baseball</a>: </p>
  </div>

  {% assign transactions = site.data.roster.brewers_transactions_current %}
  {% assign players_roster = site.data.roster.brewers_roster_current %}
  {% assign generic_headshot = "https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:silo:current.png/r_max/q_auto:best/v1/people/0/headshot/silo/current" %}

  <div class="transactions-grid">
    {% for transaction in transactions %}
      <div class="stat-card transaction-card">
        <div class="transaction-date">{{ transaction.date | date: "%B %-d, %Y" }}</div>

        {% if transaction.players %}
          <div class="transaction-players-container">
            {% for player_name in transaction.players %}
              {% assign player_id = transaction.player_ids[forloop.index0] %}
              <div class="player-profile-transaction">
                <div class="player-name-transaction">{{ player_name }}</div>
                {% assign roster_match = players_roster | where: "name", player_name | first %}
                {% if player_id %}
                  {% assign people_path = "/people/" | append: player_id | append: "/" %}
                  {% assign headshot = generic_headshot | replace: "/people/0/", people_path %}
                {% else %}
                  {% assign headshot = roster_match.thumb_url | default: generic_headshot %}
                {% endif %}
                <img src="{{ headshot }}" alt="{{ player_name }}" title="{{ player_name }}" class="player-avatar-transaction" loading="lazy" />
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
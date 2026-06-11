
  create view "postgres"."public_public"."mart_monthly_summary__dbt_tmp"
    
    
  as (
    with transactions as (
    select * from "postgres"."public_public"."int_transactions_cleaned"
    where transaction_type = 'debit'
),
monthly_summary as (
    select 
        transaction_month,
        count(*) as total_transactions,
        round(sum(amount),2) as total_spend,
        round(avg(amount),2) as avg_transactions,
        round(max(amount),2) as largest_transactions,
        sum(is_potential_duplicate) potential_duplicates
    from 
        transactions
    group by    
        transaction_month           
),
final as (
    select
        transaction_month,
        total_transactions,
        total_spend,
        avg_transactions,
        largest_transactions,
        potential_duplicates,
        round(total_spend - lag(total_spend) over(order by transaction_month),2) as mom_spend_change,
        round((total_spend - lag(total_spend) over(order by transaction_month))/nullif(lag(total_spend) over(order by transaction_month),0)
        *100,2) as mom_spend_pct_change
    from 
        monthly_summary
)
select * from final
order by transaction_month
  );